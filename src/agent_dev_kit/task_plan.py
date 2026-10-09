import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from agent_dev_kit.planner_contract import planner_payload_to_mapping
from agent_dev_kit.orchestration_policy import (
    RISK_REQUIRED_AGENTS,
    ProjectRoutingPolicy,
    coerce_durable_artifact,
    coerce_risk_flag,
    coerce_task_phase,
    evaluate_project_policies,
    preclassify_request,
)
from agent_dev_kit.orchestration import (
    AGENT_GATE_GUIDANCE,
    AgentGateDecision,
    OrchestrationTrace,
    RequestProfile,
    normalize_agent_key,
    validate_gate_policy,
)


class TaskPlanError(ValueError):
    pass


class DisabledAgentRequiredError(TaskPlanError):
    def __init__(self, agents: Iterable[str]) -> None:
        self.agents = tuple(sorted(set(agents)))
        super().__init__(
            "Task requires disabled agent(s): " + ", ".join(self.agents)
        )


@dataclass(slots=True)
class TaskNode:
    id: str
    agent: str
    objective: str
    phase: str = "implementation"
    depends_on: tuple[str, ...] = ()
    status: str = "pending"
    output: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TaskPlan:
    request: str
    nodes: list[TaskNode]
    required_disabled_agents: tuple[str, ...] = ()
    notes: str | None = None
    profile: RequestProfile | None = None
    agent_decisions: tuple[AgentGateDecision, ...] = ()
    trace: OrchestrationTrace | None = None
    decisions_explicit: bool = False
    independent_risk_flags: tuple[str, ...] = ()
    policy_activations: tuple[str, ...] = ()
    policy_required_agents: tuple[str, ...] = ()
    provider_calls: int = 0
    revisits: int = 0
    node_attempts: dict[str, int] = field(default_factory=dict)
    calls_avoided_by_reuse: int = 0
    execution_status: str = "planned"

    @classmethod
    def from_json(
        cls,
        payload: str,
        *,
        require_agent_decisions: bool = False,
        strict_schema: bool = False,
    ) -> "TaskPlan":
        cleaned = _strip_fenced_json(payload)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise TaskPlanError("Triage did not return valid JSON.") from exc
        return cls.from_payload(
            data,
            require_agent_decisions=require_agent_decisions,
            strict_schema=strict_schema,
        )

    @classmethod
    def from_payload(
        cls,
        payload: Any,
        *,
        require_agent_decisions: bool = False,
        strict_schema: bool = False,
    ) -> "TaskPlan":
        try:
            data = dict(planner_payload_to_mapping(payload))
        except (TypeError, ValueError) as exc:
            raise TaskPlanError(str(exc)) from exc

        if strict_schema:
            _validate_strict_plan_payload(data)

        raw_nodes = data.get("nodes") or []
        if not isinstance(raw_nodes, list):
            raise TaskPlanError("'nodes' must be a list.")

        nodes: list[TaskNode] = []
        for item in raw_nodes:
            if not isinstance(item, Mapping):
                raise TaskPlanError("Each task node must be an object.")
            nodes.append(
                TaskNode(
                    id=str(item.get("id") or "").strip(),
                    agent=normalize_agent_key(
                        str(item.get("agent") or "")
                    ),
                    objective=str(item.get("objective") or "").strip(),
                    phase=_coerce_contract(
                        coerce_task_phase,
                        str(item.get("phase") or "implementation"),
                    ),
                    depends_on=tuple(
                        str(value).strip()
                        for value in (item.get("depends_on") or [])
                    ),
                )
            )

        request = str(data.get("request") or "").strip()

        profile_data = data.get("profile") or {}
        if not isinstance(profile_data, Mapping):
            raise TaskPlanError("'profile' must be an object.")
        profile = RequestProfile(
            summary=str(profile_data.get("summary") or request).strip(),
            classification=str(
                profile_data.get("classification") or "unspecified"
            ).strip(),
            risk_flags=tuple(
                _coerce_contract(coerce_risk_flag, str(value))
                for value in (profile_data.get("risk_flags") or [])
                if str(value).strip()
            ),
            durable_artifacts=tuple(
                _coerce_contract(coerce_durable_artifact, str(value))
                for value in (profile_data.get("durable_artifacts") or [])
                if str(value).strip()
            ),
        )

        raw_decisions = data.get("agent_decisions")
        decisions_explicit = raw_decisions is not None
        if require_agent_decisions and not decisions_explicit:
            raise TaskPlanError(
                "Triage must return explicit agent_decisions for "
                "orchestrated tasks."
            )
        raw_decisions = raw_decisions or []
        if not isinstance(raw_decisions, list):
            raise TaskPlanError("'agent_decisions' must be a list.")

        decisions: list[AgentGateDecision] = []
        for item in raw_decisions:
            if not isinstance(item, Mapping):
                raise TaskPlanError(
                    "Each agent decision must be an object."
                )
            agent = normalize_agent_key(str(item.get("agent") or ""))
            reason = str(item.get("reason") or "").strip()
            gate = normalize_gate_key(
                str(item.get("gate") or "responsibility")
            )
            if not agent or not reason:
                raise TaskPlanError(
                    "Each agent decision requires agent and reason."
                )
            decisions.append(
                AgentGateDecision(
                    agent=agent,
                    selected=bool(item.get("selected")),
                    gate=gate,
                    reason=reason,
                )
            )

        required_disabled = tuple(
            normalize_agent_key(str(value))
            for value in (data.get("required_disabled_agents") or [])
        )

        plan = cls(
            request=request,
            nodes=nodes,
            required_disabled_agents=required_disabled,
            notes=(
                str(data.get("notes")).strip()
                if data.get("notes") is not None
                else None
            ),
            profile=profile,
            agent_decisions=tuple(decisions),
            decisions_explicit=decisions_explicit,
        )
        plan.validate_structure()
        return plan

    def validate_structure(self) -> None:
        if not self.request:
            raise TaskPlanError("Task plan request cannot be empty.")

        if self.profile is None:
            self.profile = RequestProfile(
                summary=self.request,
                classification="unspecified",
            )
        if not self.profile.summary:
            raise TaskPlanError("Task profile summary cannot be empty.")
        if not self.profile.classification:
            raise TaskPlanError(
                "Task profile classification cannot be empty."
            )

        ids = [node.id for node in self.nodes]
        if any(not node_id for node_id in ids):
            raise TaskPlanError("Every task node requires an id.")
        if len(ids) != len(set(ids)):
            raise TaskPlanError("Task node ids must be unique.")

        by_id = {node.id: node for node in self.nodes}

        for node in self.nodes:
            if not node.agent:
                raise TaskPlanError(
                    f"Task node '{node.id}' requires an agent."
                )
            if not node.objective:
                raise TaskPlanError(
                    f"Task node '{node.id}' requires an objective."
                )
            for dependency in node.depends_on:
                if dependency not in by_id:
                    raise TaskPlanError(
                        f"Task node '{node.id}' references unknown "
                        f"dependency '{dependency}'."
                    )
                if dependency == node.id:
                    raise TaskPlanError(
                        f"Task node '{node.id}' cannot depend on itself."
                    )

        decision_agents = [item.agent for item in self.agent_decisions]
        if len(decision_agents) != len(set(decision_agents)):
            raise TaskPlanError(
                "agent_decisions must contain one decision per agent."
            )

        if self.agent_decisions:
            selected = {
                item.agent
                for item in self.agent_decisions
                if item.selected
            }
            node_agents = {node.agent for node in self.nodes}
            if selected != node_agents:
                raise TaskPlanError(
                    "Selected agent decisions must match DAG node agents."
                )

        self._validate_acyclic(by_id)

    def validate_orchestration_policy(
        self,
        enabled_agents: Iterable[str],
        *,
        request: str | None = None,
        project_policies: Iterable[ProjectRoutingPolicy] = (),
    ) -> None:
        if not self.decisions_explicit:
            raise TaskPlanError(
                "Orchestrated plans require explicit gate decisions."
            )

        if self.profile is None:
            raise TaskPlanError("Task profile is required.")

        independent = preclassify_request(request or self.request)
        merged_risks = tuple(
            dict.fromkeys((*self.profile.risk_flags, *independent))
        )
        self.independent_risk_flags = independent
        if merged_risks != self.profile.risk_flags:
            self.profile = RequestProfile(
                summary=self.profile.summary,
                classification=self.profile.classification,
                risk_flags=merged_risks,
                durable_artifacts=self.profile.durable_artifacts,
            )

        policies = tuple(project_policies)
        evaluation = evaluate_project_policies(
            self.profile.risk_flags,
            policies,
        )
        self.policy_activations = evaluation.activated_policy_ids
        self.policy_required_agents = evaluation.required_agents

        enabled = tuple(
            normalize_agent_key(item) for item in enabled_agents
        )
        expected = {item for item in enabled if item != "triage"}
        actual = {item.agent for item in self.agent_decisions}
        missing_decisions = expected - actual
        if missing_decisions:
            raise TaskPlanError(
                "Triage omitted gate decision(s) for enabled agent(s): "
                + ", ".join(sorted(missing_decisions))
            )

        try:
            validate_gate_policy(
                profile=self.profile,
                decisions=self.agent_decisions,
                enabled_agents=enabled,
                required_disabled_agents=self.required_disabled_agents,
            )
        except ValueError as exc:
            raise TaskPlanError(str(exc)) from exc

        by_agent = {item.agent: item for item in self.agent_decisions}
        required_disabled = set(self.required_disabled_agents)
        for agent in self.policy_required_agents:
            if agent not in enabled:
                if agent not in required_disabled:
                    raise TaskPlanError(
                        "Activated project policy requires disabled agent "
                        f"'{agent}', which must be declared in "
                        "required_disabled_agents."
                    )
                continue
            decision = by_agent.get(agent)
            if decision is None or not decision.selected:
                policies_text = ", ".join(self.policy_activations)
                raise TaskPlanError(
                    f"Activated project policy ({policies_text}) requires "
                    f"selected agent '{agent}'."
                )

    def missing_agents(
        self,
        enabled_agents: Iterable[str],
    ) -> tuple[str, ...]:
        enabled = {normalize_agent_key(item) for item in enabled_agents}
        missing = set(self.required_disabled_agents)
        missing.update(
            node.agent
            for node in self.nodes
            if node.agent not in enabled
        )
        return tuple(sorted(missing))

    def validate_enabled(self, enabled_agents: Iterable[str]) -> None:
        missing = self.missing_agents(enabled_agents)
        if missing:
            raise DisabledAgentRequiredError(missing)

    def ready_nodes(self) -> list[TaskNode]:
        completed = {
            node.id for node in self.nodes if node.status == "completed"
        }
        return [
            node
            for node in self.nodes
            if node.status == "pending"
            and all(dep in completed for dep in node.depends_on)
        ]

    @property
    def is_complete(self) -> bool:
        return all(node.status == "completed" for node in self.nodes)

    def node(self, node_id: str) -> TaskNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def _validate_acyclic(self, by_id: dict[str, TaskNode]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise TaskPlanError("Task plan contains a dependency cycle.")

            visiting.add(node_id)
            for dependency in by_id[node_id].depends_on:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in by_id:
            visit(node_id)



def _strip_fenced_json(payload: str) -> str:
    cleaned = payload.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _validate_strict_plan_payload(data: Mapping[str, Any]) -> None:
    _require_exact_keys(
        data,
        required={
            "request",
            "profile",
            "agent_decisions",
            "required_disabled_agents",
            "notes",
            "nodes",
        },
        label="Task plan",
    )

    if not isinstance(data["request"], str) or not data["request"].strip():
        raise TaskPlanError("'request' must be a non-empty string.")
    if data["notes"] is not None and not isinstance(data["notes"], str):
        raise TaskPlanError("'notes' must be a string or null.")

    profile = data["profile"]
    if not isinstance(profile, Mapping):
        raise TaskPlanError("'profile' must be an object.")
    _require_exact_keys(
        profile,
        required={
            "summary",
            "classification",
            "risk_flags",
            "durable_artifacts",
        },
        label="Task profile",
    )
    for field_name in ("summary", "classification"):
        if (
            not isinstance(profile[field_name], str)
            or not profile[field_name].strip()
        ):
            raise TaskPlanError(
                f"'profile.{field_name}' must be a non-empty string."
            )
    _require_list(profile["risk_flags"], "'profile.risk_flags'")
    _require_list(
        profile["durable_artifacts"],
        "'profile.durable_artifacts'",
    )

    decisions = data["agent_decisions"]
    _require_list(decisions, "'agent_decisions'")
    for index, item in enumerate(decisions):
        if not isinstance(item, Mapping):
            raise TaskPlanError(
                f"agent_decisions[{index}] must be an object."
            )
        _require_exact_keys(
            item,
            required={"agent", "selected", "gate", "reason"},
            label=f"agent_decisions[{index}]",
        )
        if not isinstance(item["selected"], bool):
            raise TaskPlanError(
                f"agent_decisions[{index}].selected must be boolean."
            )
        for field_name in ("agent", "gate", "reason"):
            if (
                not isinstance(item[field_name], str)
                or not item[field_name].strip()
            ):
                raise TaskPlanError(
                    f"agent_decisions[{index}].{field_name} "
                    "must be a non-empty string."
                )

    required_disabled = data["required_disabled_agents"]
    _require_list(
        required_disabled,
        "'required_disabled_agents'",
    )
    if any(not isinstance(item, str) for item in required_disabled):
        raise TaskPlanError(
            "'required_disabled_agents' must contain only strings."
        )

    nodes = data["nodes"]
    _require_list(nodes, "'nodes'")
    for index, item in enumerate(nodes):
        if not isinstance(item, Mapping):
            raise TaskPlanError(f"nodes[{index}] must be an object.")
        _require_exact_keys(
            item,
            required={"id", "agent", "phase", "objective", "depends_on"},
            label=f"nodes[{index}]",
        )
        for field_name in ("id", "agent", "phase", "objective"):
            if (
                not isinstance(item[field_name], str)
                or not item[field_name].strip()
            ):
                raise TaskPlanError(
                    f"nodes[{index}].{field_name} must be a non-empty string."
                )
        _require_list(item["depends_on"], f"nodes[{index}].depends_on")
        if any(not isinstance(value, str) for value in item["depends_on"]):
            raise TaskPlanError(
                f"nodes[{index}].depends_on must contain only strings."
            )


def _require_exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    label: str,
) -> None:
    actual = set(value)
    missing = required - actual
    unknown = actual - required
    if missing:
        raise TaskPlanError(
            f"{label} missing required field(s): "
            + ", ".join(sorted(missing))
        )
    if unknown:
        raise TaskPlanError(
            f"{label} contains unknown field(s): "
            + ", ".join(sorted(unknown))
        )


def _require_list(value: Any, label: str) -> None:
    if not isinstance(value, list):
        raise TaskPlanError(f"{label} must be a list.")

def _coerce_contract(coercer, value: str) -> str:
    try:
        return coercer(value)
    except ValueError as exc:
        raise TaskPlanError(str(exc)) from exc


def normalize_gate_key(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
    )


def render_risk_agent_map(enabled_agents: Iterable[str]) -> str:
    """Render the deterministic risk -> agent gate map for planner prompts.

    The validator enforces RISK_REQUIRED_AGENTS; the planner must see the same
    map so it does not have to guess it (M-083).
    """

    enabled = {normalize_agent_key(item) for item in enabled_agents}
    lines = []
    for risk, agents in RISK_REQUIRED_AGENTS.items():
        rendered = ", ".join(
            agent if agent in enabled else f"{agent} (disabled)"
            for agent in agents
        )
        lines.append(f"  - {risk} -> {rendered}")
    return "\n".join(lines)


def build_planning_prompt(
    request: str,
    *,
    enabled_agents: Iterable[str],
    available_agents: Iterable[str],
    project_policies: Iterable[ProjectRoutingPolicy] = (),
) -> str:
    enabled = tuple(normalize_agent_key(item) for item in enabled_agents)
    available = tuple(normalize_agent_key(item) for item in available_agents)
    disabled = tuple(item for item in available if item not in set(enabled))
    specialists = tuple(item for item in enabled if item != "triage")

    gate_lines = "\n".join(
        f"- {agent}: {AGENT_GATE_GUIDANCE.get(agent, 'Use only when materially required.')}"
        for agent in specialists
    )
    policy_lines = "\n".join(
        "- "
        + policy.id
        + ": any_risk_flags="
        + ",".join(policy.any_risk_flags)
        + "; all_risk_flags="
        + ",".join(policy.all_risk_flags)
        + "; require_agents="
        + ",".join(policy.require_agents)
        for policy in project_policies
    )
    risk_lines = render_risk_agent_map(enabled)

    return f"""Planning-only operation. Do not hand off.

Analyze the user request and return the MINIMUM SUFFICIENT task execution DAG
as JSON only. Every specialist call has cost. Never select an agent merely
because it is available.

User request:
{request}

Enabled agent keys:
{", ".join(enabled) or "(none)"}

Known but disabled agent keys:
{", ".join(disabled) or "(none)"}

Gate policy for enabled specialists:
{gate_lines or "(none)"}

Deterministic project policies (enforced independently after planning):
{policy_lines or "(none)"}

Rules:
- Use responsibilities, not technologies, to choose agents.
- Return one explicit selected/omitted decision for EVERY enabled specialist
  except triage. Every decision requires a concise reason.
- Selected decisions must match exactly the specialist agents present in nodes.
- Never substitute a disabled specialist with another agent.
- If a disabled specialist is materially required, add it to
  required_disabled_agents and do not assign its work elsewhere.
- Risk flags are material gates, not generic labels. Canonical flags:
  functional_ambiguity, backlog_coordination, cross_layer, ux_change,
  backend_change, frontend_change, persistence_change, security_surface,
  behavior_regression, technical_review, deployment_change,
  performance_risk, runtime_reliability, analytics_data, auth_change,
  schema_change, public_api_change, sensitive_data.
- A declared risk flag requires its responsible enabled specialist, selected
  AND present in nodes. Map (risk flag -> required agents):
{risk_lines}
- Before answering, check consistency: for every flag in risk_flags, its
  required agents must be selected with a node. If you do not want to select
  that agent, the flag is not materially present: remove the flag instead.
- Critical risks are also preclassified deterministically after Triage; omitting
  them here cannot bypass their required specialists.
- Matching project policies can only add required specialists. If one is
  disabled, declare it in required_disabled_agents.
- Durable artifact names: functional_spec, technical_spec, adr, runbook,
  release_notes, project_docs.
- Any durable artifact requires Documentation when enabled.
- functional_spec requires Product when enabled.
- technical_spec or adr requires Architecture when enabled.
- runbook requires DevOps when enabled.
- Do NOT select Documentation merely to narrate every subtask.
- Do NOT select Testing merely because code changed. Select it when changed
  behavior, regression risk, logic, contracts, integrations, edge cases, or
  defined security/accessibility checks justify repeatable validation.
- Do NOT select Security without material security/privacy surface.
- Do NOT select Architecture for a tiny local change with no structural impact.
- Create independent branches when work can proceed independently.
- Express ordering only through depends_on.
- Prefer direct specialist-to-specialist flow when the dependency is clear.
- Do not create a human-QA node; human QA happens after the DAG.
- Keep nodes cohesive. Avoid duplicate responsibility and revisiting agents
  without new information.

Return exactly this shape:
{{
  "request": "...",
  "profile": {{
    "summary": "short non-sensitive factual summary",
    "classification": "short stable category",
    "risk_flags": ["behavior_regression"],
    "durable_artifacts": []
  }},
  "agent_decisions": [
    {{
      "agent": "architecture",
      "selected": false,
      "gate": "cross_layer",
      "reason": "No structural or cross-layer change."
    }}
  ],
  "required_disabled_agents": [],
  "notes": "...",
  "nodes": [
    {{
      "id": "backend",
      "agent": "backend",
      "phase": "implementation",
      "objective": "...",
      "depends_on": []
    }}
  ]
}}
"""
