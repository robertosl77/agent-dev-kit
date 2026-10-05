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
    fingerprint_routing,
)
from agent_dev_kit.task_plan import (
    TaskNode,
    TaskPlan,
    TaskPlanError,
    build_planning_prompt,
)


@dataclass(slots=True)
class DevAgentKit:
    """Runtime-ready set of enabled agents for one consuming project."""

    config: ProjectAgentDevKitConfig
    provider: AgentProvider
    agents: dict[str, AgentHandle]
    planner_agent: AgentHandle | None = None
    trace_store: OrchestrationTraceStore | None = None

    @classmethod
    def build(
        cls,
        config: ProjectAgentDevKitConfig,
        provider: AgentProvider,
        *,
        tool_registry: ToolRegistry | None = None,
        preference_profile: PreferenceProfile | None = None,
    ) -> "DevAgentKit":
        trace_store = None
        if config.orchestration.trace_enabled and config.project_root is not None:
            trace_path = (
                config.project_root / config.orchestration.trace_path
            )
            trace_store = OrchestrationTraceStore(trace_path)

        agents = create_enabled_agents(
            provider,
            config,
            tool_registry=tool_registry,
            preference_profile=preference_profile,
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
        self._validate_planner_result(planner, result)

        try:
            plan = self._parse_planner_output(result.output)
        except TaskPlanError as first_error:
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
            self._validate_planner_result(planner, repaired)
            try:
                plan = self._parse_planner_output(repaired.output)
            except TaskPlanError as second_error:
                raise TaskPlanError(
                    "Planner output remained invalid after one repair "
                    f"attempt: {second_error}"
                ) from second_error

        planning_ms = (perf_counter() - started) * 1000
        plan.request = request
        plan.provider_calls = planning_calls
        plan.validate_orchestration_policy(
            self.agents.keys(),
            request=plan.request,
            project_policies=self.config.orchestration.policies,
        )
        self._ensure_dag_budget(plan, stage="planning")
        plan.trace = self._build_trace(
            plan,
            request=request,
            planning_ms=planning_ms,
            planning_calls=planning_calls,
        )
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
        self._validate_planner_result(planner, result)

        try:
            plan = self._parse_planner_output(result.output)
        except TaskPlanError as first_error:
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
            self._validate_planner_result(planner, repaired)
            try:
                plan = self._parse_planner_output(repaired.output)
            except TaskPlanError as second_error:
                raise TaskPlanError(
                    "Planner output remained invalid after one repair "
                    f"attempt: {second_error}"
                ) from second_error

        planning_ms = (perf_counter() - started) * 1000
        plan.request = request
        plan.provider_calls = planning_calls
        plan.validate_orchestration_policy(
            self.agents.keys(),
            request=plan.request,
            project_policies=self.config.orchestration.policies,
        )
        self._ensure_dag_budget(plan, stage="planning")
        plan.trace = self._build_trace(
            plan,
            request=request,
            planning_ms=planning_ms,
            planning_calls=planning_calls,
        )
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
            "Previous output:\n"
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
        """Execute ready DAG nodes sequentially while respecting dependencies."""

        plan.validate_structure()
        plan.validate_orchestration_policy(
            self.agents.keys(),
            request=plan.request,
            project_policies=self.config.orchestration.policies,
        )
        plan.validate_enabled(self.agents.keys())
        if plan.trace is not None:
            plan.trace.status = "executing"

        while not plan.is_complete:
            ready = plan.ready_nodes()
            if not ready:
                raise TaskPlanError(
                    "Task plan has pending nodes but none are executable."
                )

            for node in ready:
                self._execute_node_sync(plan, node, session=session)

        self._complete_trace(plan)
        return plan

    async def execute_plan(
        self,
        plan: TaskPlan,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Async provider execution with deterministic DAG sequencing."""

        plan.validate_structure()
        plan.validate_orchestration_policy(
            self.agents.keys(),
            request=plan.request,
            project_policies=self.config.orchestration.policies,
        )
        plan.validate_enabled(self.agents.keys())
        if plan.trace is not None:
            plan.trace.status = "executing"

        while not plan.is_complete:
            ready = plan.ready_nodes()
            if not ready:
                raise TaskPlanError(
                    "Task plan has pending nodes but none are executable."
                )

            for node in ready:
                await self._execute_node(plan, node, session=session)

        self._complete_trace(plan)
        return plan

    def _execute_node_sync(
        self,
        plan: TaskPlan,
        node: TaskNode,
        *,
        session: Any | None,
    ) -> None:
        handle = self.agents[node.agent]
        node.status = "running"
        started = perf_counter()
        if plan.trace is not None:
            attempts = plan.trace.node_attempts.get(node.id, 0) + 1
            plan.trace.node_attempts[node.id] = attempts
            plan.trace.model_calls += 1
            if attempts > 1:
                plan.trace.revisits += 1
        try:
            result = self.provider.run_sync(
                handle,
                self._node_prompt(plan, node),
                session=session,
            )
        except Exception:
            node.status = "pending"
            if plan.trace is not None:
                plan.trace.status = "interrupted"
                plan.trace.node_durations_ms[node.id] = (
                    perf_counter() - started
                ) * 1000
            raise

        if result.active_agent.name != handle.name:
            node.status = "blocked"
            if plan.trace is not None:
                plan.trace.handoffs += 1
                plan.trace.status = "blocked"
                plan.trace.node_durations_ms[node.id] = (
                    perf_counter() - started
                ) * 1000
            raise TaskPlanError(
                f"Node '{node.id}' handed off unexpectedly from "
                f"'{handle.name}' to '{result.active_agent.name}'. "
                "The task DAG owns cross-specialist sequencing."
            )

        node.output = result.output
        node.evidence = {
            "provider": self.provider.key,
            "active_agent": result.active_agent.name,
        }
        node.status = "completed"
        if plan.trace is not None:
            plan.trace.node_durations_ms[node.id] = (
                perf_counter() - started
            ) * 1000

    async def _execute_node(
        self,
        plan: TaskPlan,
        node: TaskNode,
        *,
        session: Any | None,
    ) -> None:
        handle = self.agents[node.agent]
        node.status = "running"
        started = perf_counter()
        if plan.trace is not None:
            attempts = plan.trace.node_attempts.get(node.id, 0) + 1
            plan.trace.node_attempts[node.id] = attempts
            plan.trace.model_calls += 1
            if attempts > 1:
                plan.trace.revisits += 1
        try:
            result = await self.provider.run(
                handle,
                self._node_prompt(plan, node),
                session=session,
            )
        except Exception:
            node.status = "pending"
            if plan.trace is not None:
                plan.trace.status = "interrupted"
                plan.trace.node_durations_ms[node.id] = (
                    perf_counter() - started
                ) * 1000
            raise

        if result.active_agent.name != handle.name:
            node.status = "blocked"
            if plan.trace is not None:
                plan.trace.handoffs += 1
                plan.trace.status = "blocked"
                plan.trace.node_durations_ms[node.id] = (
                    perf_counter() - started
                ) * 1000
            raise TaskPlanError(
                f"Node '{node.id}' handed off unexpectedly from "
                f"'{handle.name}' to '{result.active_agent.name}'. "
                "The task DAG owns cross-specialist sequencing."
            )

        node.output = result.output
        node.evidence = {
            "provider": self.provider.key,
            "active_agent": result.active_agent.name,
        }
        node.status = "completed"
        if plan.trace is not None:
            plan.trace.node_durations_ms[node.id] = (
                perf_counter() - started
            ) * 1000

    @staticmethod
    def _node_prompt(plan: TaskPlan, node: TaskNode) -> str:
        dependency_context = []
        for dependency_id in node.depends_on:
            dependency = plan.node(dependency_id)
            dependency_context.append(
                f"[{dependency.id} / {dependency.agent}]\n"
                f"{dependency.output or '(no output)'}"
            )

        dependencies = (
            "\n\n".join(dependency_context)
            if dependency_context
            else "(none)"
        )

        return (
            "Execute only this DAG node. Do not hand off to another "
            "specialist; cross-specialist sequencing is owned by the task "
            "plan. If another responsibility is required, report it as a "
            "blocker.\n\n"
            f"Task summary:\n{plan.profile.summary if plan.profile else plan.request}\n\n"
            f"Node id: {node.id}\n"
            f"Phase: {node.phase}\n"
            f"Your responsibility: {node.agent}\n"
            f"Objective:\n{node.objective}\n\n"
            f"Completed dependency outputs:\n{dependencies}\n\n"
            "Return the node result and concise evidence useful to the "
            "following nodes and final documentation."
        )

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
            node_durations_ms={"__planning__": planning_ms},
            status="planned",
        )

    def _complete_trace(self, plan: TaskPlan) -> None:
        if plan.trace is None:
            return

        plan.trace.status = "completed"
        if self.trace_store is not None and not plan.trace.persisted:
            self.trace_store.append(plan.trace)

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
