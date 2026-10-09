import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from typing import Any

from agent_dev_kit.agent_catalog import (
    AVAILABLE_AGENT_KEYS,
    build_enabled_definitions,
    create_enabled_agents,
)
from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.planner_contract import StructuredTaskPlan
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider, ProviderRunResult
from agent_dev_kit.tooling import ToolRegistry
from agent_dev_kit.preferences import PreferenceProfile
from agent_dev_kit.orchestration_budget import OrchestrationBudgetExceeded
from agent_dev_kit.orchestration import (
    OrchestrationTrace,
    OrchestrationTraceStore,
    fingerprint_request,
    fingerprint_intake,
    fingerprint_routing,
    resolve_project_trace_path,
)
from agent_dev_kit.task_plan import (
    DisabledAgentRequiredError,
    TaskNode,
    TaskPlan,
    TaskPlanError,
    build_planning_prompt,
    render_risk_agent_map,
)


MAX_REQUEST_IN_NODE_CHARS = 4000
MAX_REJECTED_OUTPUT_CHARS = 20000
_PLAN_SLOT = "\x00plan-context\x00"
PLANNER_REJECTIONS_FILENAME = "planner-rejections.jsonl"
_GATE_ERROR_PATTERN = re.compile(
    r"((?:Risk|Artifact) '[^']+') requires selected agent '([^']+)'"
)


@dataclass(slots=True)
class DevAgentKit:
    """Runtime-ready set of enabled agents for one consuming project."""

    config: ProjectAgentDevKitConfig
    provider: AgentProvider
    agents: dict[str, AgentHandle]
    planner_agent: AgentHandle | None = None
    trace_store: OrchestrationTraceStore | None = None
    rejection_log_path: Path | None = None
    execution_note: str = ""
    mode: str = "propose"

    @classmethod
    def build(
        cls,
        config: ProjectAgentDevKitConfig,
        provider: AgentProvider,
        *,
        tool_registry: ToolRegistry | None = None,
        preference_profile: PreferenceProfile | None = None,
        builtin_tools: Any | None = None,
        execution_note: str = "",
        mode: str = "propose",
    ) -> "DevAgentKit":
        trace_store = None
        rejection_log_path = None
        if config.orchestration.trace_enabled and config.project_root is not None:
            trace_path = resolve_project_trace_path(
                config.project_root,
                config.orchestration.trace_path,
            )
            rejection_log_path = trace_path.parent / PLANNER_REJECTIONS_FILENAME
            trace_store = OrchestrationTraceStore(
                trace_path,
                max_entries=config.orchestration.trace_max_entries,
            )

        agents = create_enabled_agents(
            provider,
            config,
            tool_registry=tool_registry,
            preference_profile=preference_profile,
            builtin_tools=builtin_tools,
        )
        planner_agent = None
        if "triage" in agents:
            triage_definition = build_enabled_definitions(
                config,
                preference_profile=preference_profile,
            )["triage"]
            planner_definition = AgentDefinition(
                name="Agent Triage Planner",
                instructions=triage_definition.instructions,
                model=triage_definition.model,
            )
            if provider.supports_structured_output():
                planner_agent = provider.create_structured_agent(
                    planner_definition,
                    output_type=StructuredTaskPlan,
                )
            else:
                planner_agent = provider.create_agent(planner_definition)

        return cls(
            config=config,
            provider=provider,
            agents=agents,
            planner_agent=planner_agent,
            trace_store=trace_store,
            rejection_log_path=rejection_log_path,
            execution_note=execution_note,
            mode=mode,
        )

    def conversation(
        self,
        *,
        session: Any | None = None,
        start_agent: str | None = None,
    ) -> "DevConversation":
        return DevConversation(
            kit=self,
            session=session,
            active_agent=self._resolve_start_agent(start_agent),
        )

    def plan_task_sync(
        self,
        request: str,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Create a validated plan within hard orchestration budgets."""

        planner = self._require_planner()
        prompt = build_planning_prompt(
            request,
            enabled_agents=self.agents.keys(),
            available_agents=AVAILABLE_AGENT_KEYS,
            project_policies=self.config.orchestration.policies,
        )
        self._ensure_prompt_budget(prompt, stage="planning")
        self._ensure_provider_call_budget(1, stage="planning")

        started = perf_counter()
        result = self.provider.run_sync(
            planner,
            prompt,
            session=session,
        )
        planning_calls = 1
        planning_usage = list(result.usage)
        self._validate_planner_result(planner, result)

        try:
            plan = self._parse_and_validate_plan(result.output, request)
        except DisabledAgentRequiredError:
            raise
        except TaskPlanError as first_error:
            self._record_planner_rejection(
                request=request,
                stage="planning",
                output=result.output,
                error=first_error,
            )
            self._ensure_provider_call_budget(2, stage="planning_repair")
            repair_prompt = self._planning_repair_prompt(
                request=request,
                invalid_output=result.output,
                error=first_error,
            )
            self._ensure_prompt_budget(
                repair_prompt,
                stage="planning_repair",
            )
            repaired = self.provider.run_sync(
                planner,
                repair_prompt,
                session=session,
            )
            planning_calls += 1
            planning_usage.extend(repaired.usage)
            self._validate_planner_result(planner, repaired)
            try:
                plan = self._parse_and_validate_plan(repaired.output, request)
            except DisabledAgentRequiredError:
                raise
            except TaskPlanError as second_error:
                saved = self._record_planner_rejection(
                    request=request,
                    stage="planning_repair",
                    output=repaired.output,
                    error=second_error,
                )
                hint = f" Salidas rechazadas en: {saved}" if saved else ""
                raise TaskPlanError(
                    "Planner output remained invalid after one repair "
                    f"attempt: {second_error}{hint}"
                ) from second_error

        planning_ms = (perf_counter() - started) * 1000
        plan.request = request
        plan.provider_calls = planning_calls
        plan.trace = self._build_trace(
            plan,
            request=request,
            planning_ms=planning_ms,
            planning_calls=planning_calls,
        )
        plan.trace.add_usage("planner", "triage", planning_usage)
        self._ensure_dag_budget(plan, stage="planning")
        return plan

    async def plan_task(
        self,
        request: str,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Async variant of budgeted structured planning."""

        planner = self._require_planner()
        prompt = build_planning_prompt(
            request,
            enabled_agents=self.agents.keys(),
            available_agents=AVAILABLE_AGENT_KEYS,
            project_policies=self.config.orchestration.policies,
        )
        self._ensure_prompt_budget(prompt, stage="planning")
        self._ensure_provider_call_budget(1, stage="planning")

        started = perf_counter()
        result = await self.provider.run(
            planner,
            prompt,
            session=session,
        )
        planning_calls = 1
        planning_usage = list(result.usage)
        self._validate_planner_result(planner, result)

        try:
            plan = self._parse_and_validate_plan(result.output, request)
        except DisabledAgentRequiredError:
            raise
        except TaskPlanError as first_error:
            self._record_planner_rejection(
                request=request,
                stage="planning",
                output=result.output,
                error=first_error,
            )
            self._ensure_provider_call_budget(2, stage="planning_repair")
            repair_prompt = self._planning_repair_prompt(
                request=request,
                invalid_output=result.output,
                error=first_error,
            )
            self._ensure_prompt_budget(
                repair_prompt,
                stage="planning_repair",
            )
            repaired = await self.provider.run(
                planner,
                repair_prompt,
                session=session,
            )
            planning_calls += 1
            planning_usage.extend(repaired.usage)
            self._validate_planner_result(planner, repaired)
            try:
                plan = self._parse_and_validate_plan(repaired.output, request)
            except DisabledAgentRequiredError:
                raise
            except TaskPlanError as second_error:
                saved = self._record_planner_rejection(
                    request=request,
                    stage="planning_repair",
                    output=repaired.output,
                    error=second_error,
                )
                hint = f" Salidas rechazadas en: {saved}" if saved else ""
                raise TaskPlanError(
                    "Planner output remained invalid after one repair "
                    f"attempt: {second_error}{hint}"
                ) from second_error

        planning_ms = (perf_counter() - started) * 1000
        plan.request = request
        plan.provider_calls = planning_calls
        plan.trace = self._build_trace(
            plan,
            request=request,
            planning_ms=planning_ms,
            planning_calls=planning_calls,
        )
        plan.trace.add_usage("planner", "triage", planning_usage)
        self._ensure_dag_budget(plan, stage="planning")
        return plan

    def _require_planner(self) -> AgentHandle:
        if "triage" not in self.agents or self.planner_agent is None:
            raise ValueError(
                "Triage must be enabled to create a multi-agent task plan."
            )
        return self.planner_agent

    @staticmethod
    def _validate_planner_result(
        planner: AgentHandle,
        result: ProviderRunResult,
    ) -> None:
        if (
            result.active_agent.native is not planner.native
            and result.active_agent.name != planner.name
        ):
            raise TaskPlanError(
                "Planner handed off unexpectedly during planning. "
                "Planning must execute without handoffs."
            )

    def _parse_and_validate_plan(self, output: Any, request: str) -> TaskPlan:
        """Parse and validate gates, so both kinds of error get one repair."""

        plan = self._parse_planner_output(output)
        plan.request = request
        plan.validate_orchestration_policy(
            self.agents.keys(),
            request=request,
            project_policies=self.config.orchestration.policies,
        )
        return plan

    @staticmethod
    def _parse_planner_output(output: Any) -> TaskPlan:
        if isinstance(output, str):
            return TaskPlan.from_json(
                output,
                require_agent_decisions=True,
                strict_schema=True,
            )
        return TaskPlan.from_payload(
            output,
            require_agent_decisions=True,
            strict_schema=True,
        )

    def _record_planner_rejection(
        self,
        *,
        request: str,
        stage: str,
        output: Any,
        error: TaskPlanError,
    ) -> Path | None:
        """Append a rejected planner output to the local JSONL log (M-083).

        Best-effort diagnostics: a logging failure never hides the planning
        error. Lives next to the orchestration traces (gitignored runtime dir).
        """

        path = self.rejection_log_path
        if path is None:
            return None
        rendered = output if isinstance(output, str) else _render_output(output)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "error": str(error),
            "request_fingerprint": fingerprint_request(request),
            "output": self._truncate_text(rendered, MAX_REJECTED_OUTPUT_CHARS),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            return None
        return path

    def _gate_repair_guidance(self, error: TaskPlanError) -> str:
        """Spell out the valid exits for a risk/artifact gate error (M-083)."""

        match = _GATE_ERROR_PATTERN.search(str(error))
        if match is None:
            return ""
        source, agent = match.group(1), match.group(2)
        return (
            f"How to fix this gate error ({source} -> '{agent}'), choose ONE:\n"
            f"  a) If {source} is not materially present in the request, "
            "remove it from the profile and keep the rest of the plan.\n"
            f"  b) If it is present, set agent '{agent}' to selected: true "
            f"AND add a node with agent '{agent}' (usually phase analysis) "
            "wired with depends_on where it feeds other nodes.\n"
            "Do not keep the flag while omitting the agent: that is the same "
            "invalid plan again.\n"
            "Risk flag -> required agents:\n"
            + render_risk_agent_map(self.agents.keys())
            + "\n\n"
        )

    def _planning_repair_prompt(
        self,
        *,
        request: str,
        invalid_output: Any,
        error: TaskPlanError,
    ) -> str:
        budget = self.config.orchestration.budgets.max_context_chars
        fixed = (
            "Planning repair operation. Do not hand off. The previous planner "
            "output violated the strict TaskPlan contract. Return the complete "
            "corrected TaskPlan only; do not explain the repair.\n\n"
            f"Original request:\n{request}\n\n"
            f"Validation error:\n{error}\n\n"
            "agent_decisions must contain exactly one decision (selected true "
            "or false, gate and reason) for EACH of these agents: "
            + ", ".join(key for key in self.agents if key != "triage")
            + ".\n\n"
            + self._gate_repair_guidance(error)
            + "Previous output:\n"
        )
        available = budget - len(fixed)
        if available <= 0:
            raise OrchestrationBudgetExceeded(
                budget="max_context_chars",
                limit=budget,
                actual=len(fixed),
                stage="planning_repair",
                message=(
                    "Planning repair metadata alone exceeds the context budget."
                ),
            )
        rendered = self._truncate_text(str(invalid_output), available)
        return fixed + rendered

    def _ensure_provider_call_budget(
        self,
        actual: int,
        *,
        stage: str,
    ) -> None:
        limit = self.config.orchestration.budgets.max_provider_calls
        if actual > limit:
            raise OrchestrationBudgetExceeded(
                budget="max_provider_calls",
                limit=limit,
                actual=actual,
                stage=stage,
            )

    def _ensure_prompt_budget(
        self,
        prompt: str,
        *,
        stage: str,
    ) -> None:
        limit = self.config.orchestration.budgets.max_context_chars
        if len(prompt) > limit:
            raise OrchestrationBudgetExceeded(
                budget="max_context_chars",
                limit=limit,
                actual=len(prompt),
                stage=stage,
            )

    def _ensure_dag_budget(
        self,
        plan: TaskPlan,
        *,
        stage: str,
    ) -> None:
        limit = self.config.orchestration.budgets.max_dag_nodes
        actual = len(plan.nodes)
        if actual > limit:
            self._raise_budget(
                plan,
                budget="max_dag_nodes",
                limit=limit,
                actual=actual,
                stage=stage,
            )

    def execute_plan_sync(
        self,
        plan: TaskPlan,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Execute ready DAG nodes within deterministic hard budgets."""

        try:
            self._prepare_plan_execution(plan)
        except OrchestrationBudgetExceeded:
            raise
        except DisabledAgentRequiredError:
            plan.execution_status = "blocked"
            self._persist_trace(plan, "blocked")
            raise
        except Exception:
            plan.execution_status = "failed"
            self._persist_trace(plan, "failed")
            raise

        while not plan.is_complete:
            ready = plan.ready_nodes()
            if not ready:
                plan.execution_status = "failed"
                self._persist_trace(plan, "failed")
                raise TaskPlanError(
                    "Task plan has pending nodes but none are executable."
                )

            for node in ready:
                if self._reuse_completed_node(plan, node):
                    continue
                self._execute_node_sync(plan, node, session=session)

        self._complete_trace(plan)
        return plan

    async def execute_plan(
        self,
        plan: TaskPlan,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Async provider execution with deterministic hard budgets."""

        try:
            self._prepare_plan_execution(plan)
        except OrchestrationBudgetExceeded:
            raise
        except DisabledAgentRequiredError:
            plan.execution_status = "blocked"
            self._persist_trace(plan, "blocked")
            raise
        except Exception:
            plan.execution_status = "failed"
            self._persist_trace(plan, "failed")
            raise

        while not plan.is_complete:
            ready = plan.ready_nodes()
            if not ready:
                plan.execution_status = "failed"
                self._persist_trace(plan, "failed")
                raise TaskPlanError(
                    "Task plan has pending nodes but none are executable."
                )

            for node in ready:
                if self._reuse_completed_node(plan, node):
                    continue
                await self._execute_node(plan, node, session=session)

        self._complete_trace(plan)
        return plan

    def _prepare_plan_execution(self, plan: TaskPlan) -> None:
        plan.validate_structure()
        plan.validate_orchestration_policy(
            self.agents.keys(),
            request=plan.request,
            project_policies=self.config.orchestration.policies,
        )
        plan.validate_enabled(self.agents.keys())
        self._ensure_dag_budget(plan, stage="execution")
        plan.execution_status = "executing"
        if plan.trace is not None:
            plan.trace.status = "executing"

    def _execute_node_sync(
        self,
        plan: TaskPlan,
        node: TaskNode,
        *,
        session: Any | None,
    ) -> None:
        handle = self.agents[node.agent]
        started = perf_counter()
        attempt = self._check_node_attempt_budget(plan, node)
        prompt = self._node_prompt(plan, node)
        self._record_node_attempt(plan, node, attempt)
        node.status = "running"

        try:
            result = self.provider.run_sync(
                handle,
                prompt,
                session=session,
            )
        except Exception:
            node.status = "pending"
            plan.execution_status = "interrupted"
            if plan.trace is not None:
                plan.trace.node_durations_ms[node.id] = (
                    perf_counter() - started
                ) * 1000
            self._persist_trace(plan, "interrupted")
            raise

        self._complete_node_result(
            plan,
            node,
            handle,
            result,
            started=started,
        )

    async def _execute_node(
        self,
        plan: TaskPlan,
        node: TaskNode,
        *,
        session: Any | None,
    ) -> None:
        handle = self.agents[node.agent]
        started = perf_counter()
        attempt = self._check_node_attempt_budget(plan, node)
        prompt = self._node_prompt(plan, node)
        self._record_node_attempt(plan, node, attempt)
        node.status = "running"

        try:
            result = await self.provider.run(
                handle,
                prompt,
                session=session,
            )
        except Exception:
            node.status = "pending"
            plan.execution_status = "interrupted"
            if plan.trace is not None:
                plan.trace.node_durations_ms[node.id] = (
                    perf_counter() - started
                ) * 1000
            self._persist_trace(plan, "interrupted")
            raise

        self._complete_node_result(
            plan,
            node,
            handle,
            result,
            started=started,
        )

    def _check_node_attempt_budget(
        self,
        plan: TaskPlan,
        node: TaskNode,
    ) -> tuple[int, int, int]:
        next_attempt = plan.node_attempts.get(node.id, 0) + 1
        next_revisits = plan.revisits + (1 if next_attempt > 1 else 0)
        revisit_limit = self.config.orchestration.budgets.max_revisits
        if next_revisits > revisit_limit:
            self._raise_budget(
                plan,
                budget="max_revisits",
                limit=revisit_limit,
                actual=next_revisits,
                stage="execution",
                node=node,
            )

        next_calls = plan.provider_calls + 1
        call_limit = self.config.orchestration.budgets.max_provider_calls
        if next_calls > call_limit:
            self._raise_budget(
                plan,
                budget="max_provider_calls",
                limit=call_limit,
                actual=next_calls,
                stage="execution",
                node=node,
            )

        return next_attempt, next_revisits, next_calls

    @staticmethod
    def _record_node_attempt(
        plan: TaskPlan,
        node: TaskNode,
        attempt: tuple[int, int, int],
    ) -> None:
        next_attempt, next_revisits, next_calls = attempt
        plan.node_attempts[node.id] = next_attempt
        plan.provider_calls = next_calls
        if next_attempt > 1:
            plan.revisits = next_revisits

        if plan.trace is not None:
            plan.trace.node_attempts[node.id] = next_attempt
            plan.trace.provider_calls = plan.provider_calls
            # M-036 will distinguish provider runs from real model requests.
            plan.trace.model_calls = plan.provider_calls
            plan.trace.revisits = plan.revisits

    def _complete_node_result(
        self,
        plan: TaskPlan,
        node: TaskNode,
        handle: AgentHandle,
        result: ProviderRunResult,
        *,
        started: float,
    ) -> None:
        if result.active_agent.name != handle.name:
            node.status = "blocked"
            plan.execution_status = "blocked"
            if plan.trace is not None:
                plan.trace.handoffs += 1
                plan.trace.node_durations_ms[node.id] = (
                    perf_counter() - started
                ) * 1000
            self._persist_trace(plan, "blocked")
            raise TaskPlanError(
                f"Node '{node.id}' handed off unexpectedly from "
                f"'{handle.name}' to '{result.active_agent.name}'. "
                "The task DAG owns cross-specialist sequencing."
            )

        node.output = result.output
        if plan.trace is not None:
            plan.trace.add_usage(node.id, node.agent, result.usage)
        node.evidence = {
            "provider": self.provider.key,
            "active_agent": result.active_agent.name,
        }
        node.status = "completed"
        if plan.trace is not None:
            plan.trace.node_durations_ms[node.id] = (
                perf_counter() - started
            ) * 1000

    def _reuse_completed_node(
        self,
        plan: TaskPlan,
        node: TaskNode,
    ) -> bool:
        fingerprint = self._node_input_fingerprint(plan, node)
        for candidate in plan.nodes:
            if candidate is node or candidate.status != "completed":
                continue
            if candidate.output is None:
                continue
            if self._node_input_fingerprint(plan, candidate) != fingerprint:
                continue

            node.output = candidate.output
            node.evidence = dict(candidate.evidence)
            node.evidence["reused_from"] = candidate.id
            node.evidence["reuse_fingerprint"] = fingerprint
            node.status = "completed"
            plan.calls_avoided_by_reuse += 1
            if plan.trace is not None:
                plan.trace.calls_avoided_by_reuse = (
                    plan.calls_avoided_by_reuse
                )
                plan.trace.node_durations_ms[node.id] = 0.0
            return True
        return False

    @staticmethod
    def _node_input_fingerprint(plan: TaskPlan, node: TaskNode) -> str:
        dependency_inputs = []
        for dependency_id in node.depends_on:
            dependency = plan.node(dependency_id)
            dependency_inputs.append(
                (
                    dependency.agent,
                    str(dependency.output or ""),
                )
            )
        payload = repr(
            (
                plan.profile.summary if plan.profile else plan.request,
                node.agent,
                node.phase,
                " ".join(node.objective.split()),
                tuple(sorted(dependency_inputs)),
            )
        ).encode("utf-8")
        return sha256(payload).hexdigest()[:24]

    def _node_prompt(self, plan: TaskPlan, node: TaskNode) -> str:
        summary = plan.profile.summary if plan.profile else plan.request
        request = self._truncate_text(plan.request or "", MAX_REQUEST_IN_NODE_CHARS)
        language_rule = (
            ""
            if self.config.language
            else (
                "Language: write every text meant for people (answers, "
                "documents, comments, reports) in the same language as the "
                "original request below. Keep code, identifiers, file names, "
                "commands and branch names unchanged.\n\n"
            )
        )
        prefix = (
            "Execute only this DAG node. Do not hand off to another "
            "specialist; cross-specialist sequencing is owned by the task "
            "plan. If another responsibility is required, report it as a "
            "blocker.\n\n"
            + language_rule
            + "Original request from the person (source of truth: every "
            "explicit requirement in it must be met exactly; the summary and "
            "objective below only scope your part):\n"
            f"{request}\n\n"
            "Do not invent people, roles, processes, rules, facts or "
            "examples that are not in the request, the referenced issue or "
            "the repository. If something is missing, say so instead of "
            "assuming it.\n\n"
            f"Task summary:\n{summary}\n\n"
            + _PLAN_SLOT
            + f"Node id: {node.id}\n"
            f"Phase: {node.phase}\n"
            f"Your responsibility: {node.agent}\n"
            f"Objective:\n{node.objective}\n\n"
            "Completed dependency outputs:\n"
        )
        suffix = (
            (f"\n\n{self.execution_note}" if self.execution_note else "")
            + "\n\nReturn the node result and concise evidence useful to the "
            "following nodes and final documentation."
        )

        context_limit = self.config.orchestration.budgets.max_context_chars
        mandatory = prefix.replace(_PLAN_SLOT, "")
        available = context_limit - len(mandatory) - len(suffix)
        if available < 0:
            self._raise_budget(
                plan,
                budget="max_context_chars",
                limit=context_limit,
                actual=len(mandatory) + len(suffix),
                stage="execution",
                node=node,
                message=(
                    "Mandatory node context exceeds max_context_chars before "
                    "dependency evidence is included."
                ),
            )

        # The real plan (M-084) is useful but optional: dependency evidence
        # keeps priority, and the plan is included only when it fits whole.
        evidence_reserve = min(
            self.config.orchestration.budgets.max_dependency_evidence_chars,
            available,
        )
        plan_context = self._plan_context(plan)
        if len(plan_context) > available - evidence_reserve:
            plan_context = ""
        prefix = prefix.replace(_PLAN_SLOT, plan_context)
        available -= len(plan_context)

        evidence_limit = min(
            self.config.orchestration.budgets.max_dependency_evidence_chars,
            available,
        )
        dependencies, deduplicated, truncated = (
            self._dependency_context(
                plan,
                node,
                limit=evidence_limit,
            )
        )
        prompt = prefix + dependencies + suffix

        if plan.trace is not None:
            plan.trace.deduplicated_context_items += deduplicated
            if truncated:
                plan.trace.context_truncations += 1
            plan.trace.context_chars_total += len(prompt)
            plan.trace.max_context_chars_observed = max(
                plan.trace.max_context_chars_observed,
                len(prompt),
            )

        return prompt

    @staticmethod
    def _plan_context(plan: TaskPlan) -> str:
        """The real plan decided by Triage, so nodes report it as-is (M-084)."""

        def short(text: str, limit: int = 240) -> str:
            text = " ".join(str(text or "").split())
            return text if len(text) <= limit else text[: limit - 3] + "..."

        selected = [item for item in plan.agent_decisions if item.selected]
        omitted = [item for item in plan.agent_decisions if not item.selected]
        lines = [
            "Task plan decided by Triage (the planner). If you must report the "
            "plan or the selected/omitted agents, copy this exactly; do not "
            "reconstruct it. Triage is the planner, not a candidate agent."
        ]
        lines.append("Selected agents:")
        lines.extend(
            f"- {item.agent}: {short(item.reason)}" for item in selected
        )
        if not selected:
            lines.append("- (none)")
        lines.append("Omitted agents:")
        lines.extend(
            f"- {item.agent}: {short(item.reason)}" for item in omitted
        )
        if not omitted:
            lines.append("- (none)")
        if plan.required_disabled_agents:
            lines.append(
                "Required but disabled: "
                + ", ".join(plan.required_disabled_agents)
            )
        lines.append("Nodes:")
        for item in plan.nodes:
            after = (
                f" (after {', '.join(item.depends_on)})"
                if item.depends_on
                else ""
            )
            lines.append(
                f"- {item.id} [{item.agent}, {item.phase}]{after}: "
                f"{short(item.objective)}"
            )
        return "\n".join(lines) + "\n\n"

    def _dependency_context(
        self,
        plan: TaskPlan,
        node: TaskNode,
        *,
        limit: int,
    ) -> tuple[str, int, bool]:
        if not node.depends_on:
            raw = "(none)"
            clipped = self._truncate_text(raw, limit)
            return clipped, 0, clipped != raw

        groups: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        deduplicated = 0
        for dependency_id in node.depends_on:
            dependency = plan.node(dependency_id)
            output = str(dependency.output or "(no output)")
            key = sha256(output.encode("utf-8")).hexdigest()
            existing = groups.get(key)
            if existing is not None and existing["output"] == output:
                existing["labels"].append(
                    f"{dependency.id} / {dependency.agent}"
                )
                deduplicated += 1
                continue
            groups[key] = {
                "output": output,
                "labels": [f"{dependency.id} / {dependency.agent}"],
            }
            order.append(key)

        blocks = []
        for key in order:
            item = groups[key]
            labels = "; ".join(item["labels"])
            blocks.append(f"[{labels}]\n{item['output']}")
        raw = "\n\n".join(blocks)
        clipped = self._truncate_text(raw, limit)
        return clipped, deduplicated, clipped != raw

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text

        marker = "\n...[truncated by orchestration budget]...\n"
        if limit <= len(marker):
            return marker[:limit]

        remaining = limit - len(marker)
        head = (remaining * 2) // 3
        tail = remaining - head
        return text[:head] + marker + text[-tail:]

    def _raise_budget(
        self,
        plan: TaskPlan,
        *,
        budget: str,
        limit: int,
        actual: int,
        stage: str,
        node: TaskNode | None = None,
        message: str | None = None,
    ) -> None:
        error = OrchestrationBudgetExceeded(
            budget=budget,
            limit=limit,
            actual=actual,
            stage=stage,
            message=message,
        )
        plan.execution_status = error.status
        if node is not None:
            node.status = "blocked"
        if plan.trace is not None:
            plan.trace.budget_events.append(error.to_dict())
        self._persist_trace(plan, error.status)
        raise error

    def _build_trace(
        self,
        plan: TaskPlan,
        *,
        request: str,
        planning_ms: float,
        planning_calls: int = 1,
    ) -> OrchestrationTrace:
        profile = plan.profile
        if profile is None:
            raise TaskPlanError("Task profile is required for orchestration trace.")

        return OrchestrationTrace(
            request_summary=profile.summary,
            request_fingerprint=fingerprint_request(
                request,
                profile.classification,
            ),
            classification=profile.classification,
            risk_flags=profile.risk_flags,
            durable_artifacts=profile.durable_artifacts,
            agent_decisions=plan.agent_decisions,
            dag=tuple(
                {
                    "id": node.id,
                    "agent": node.agent,
                    "phase": node.phase,
                    "depends_on": list(node.depends_on),
                }
                for node in plan.nodes
            ),
            routing_fingerprint=fingerprint_routing(profile),
            independent_risk_flags=plan.independent_risk_flags,
            policy_activations=plan.policy_activations,
            full_request=(
                request
                if self.config.orchestration.persist_full_request
                else None
            ),
            model_calls=planning_calls,
            provider_calls=planning_calls,
            node_durations_ms={"__planning__": planning_ms},
            status="planned",
            provider=self.provider.key,
            model=self.config.provider.default_model or "",
            mode=self.mode,
            intake_key=fingerprint_intake(
                plan.independent_risk_flags,
                self.agents.keys(),
            ),
            recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            run_id=uuid4().hex[:12],
        )

    def record_plan_only(self, plan: TaskPlan) -> None:
        """Persist the trace of a /plan run (planning without execution)."""

        plan.execution_status = "planned_only"
        self._persist_trace(plan, "planned_only")

    def _complete_trace(self, plan: TaskPlan) -> None:
        plan.execution_status = "completed"
        self._persist_trace(plan, "completed")

    def _persist_trace(self, plan: TaskPlan, status: str) -> None:
        trace = plan.trace
        if trace is None:
            return

        trace.status = status
        if (
            self.trace_store is not None
            and trace.last_persisted_status != status
        ):
            self.trace_store.append(trace)

    def _resolve_start_agent(self, start_agent: str | None) -> AgentHandle:
        if start_agent is not None:
            try:
                return self.agents[start_agent]
            except KeyError as exc:
                raise ValueError(
                    f"Agent '{start_agent}' is not enabled in this project."
                ) from exc

        if "triage" in self.agents:
            return self.agents["triage"]

        if len(self.agents) == 1:
            return next(iter(self.agents.values()))

        raise ValueError(
            "No Triage agent is enabled and more than one specialist is active. "
            "Specify start_agent explicitly."
        )


@dataclass(slots=True)
class DevConversation:
    """Conversation that persists the last active specialist between turns."""

    kit: DevAgentKit
    session: Any | None
    active_agent: AgentHandle

    async def ask(self, message: str) -> ProviderRunResult:
        result = await self.kit.provider.run(
            self.active_agent,
            message,
            session=self.session,
        )
        self.active_agent = self._canonical_handle(result.active_agent)
        return result

    def ask_sync(self, message: str) -> ProviderRunResult:
        result = self.kit.provider.run_sync(
            self.active_agent,
            message,
            session=self.session,
        )
        self.active_agent = self._canonical_handle(result.active_agent)
        return result

    def reset_route(self) -> None:
        if "triage" not in self.kit.agents:
            raise ValueError("Triage is not enabled for this project.")
        self.active_agent = self.kit.agents["triage"]

    def route_to(self, key: str) -> None:
        try:
            self.active_agent = self.kit.agents[key]
        except KeyError as exc:
            raise ValueError(
                f"Agent '{key}' is not enabled in this project."
            ) from exc

    def _canonical_handle(self, result_handle: AgentHandle) -> AgentHandle:
        for handle in self.kit.agents.values():
            if handle.native is result_handle.native:
                return handle

        for handle in self.kit.agents.values():
            if handle.name == result_handle.name:
                return handle

        raise ValueError(
            f"Provider returned unknown active agent '{result_handle.name}'."
        )


def _render_output(output: Any) -> str:
    dump = getattr(output, "model_dump", None)
    if callable(dump):
        try:
            return json.dumps(dump(mode="json"), ensure_ascii=False)
        except (TypeError, ValueError):
            pass
    return str(output)
