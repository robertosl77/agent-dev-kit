import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from agent_dev_kit.orchestration_policy import (
    AgentDecision,
    OrchestrationPolicyError,
    normalize_gate,
    validate_plan_policy,
)
from agent_dev_kit.orchestration_trace import OrchestrationTrace


class TaskPlanError(ValueError):
    pass


class DisabledAgentRequiredError(TaskPlanError):
    def __init__(self, agents: Iterable[str]) -> None:
        self.agents = tuple(sorted(set(agents)))
        super().__init__(
            "Task requires disabled agent(s): " + ", ".join(self.agents)
        )


@dataclass(frozen=True, slots=True)
class ArtifactRequest:
    kind: str
    action: str = "update"

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise TaskPlanError("Artifact request requires kind.")
        if not self.action.strip():
            raise TaskPlanError("Artifact request requires action.")


@dataclass(slots=True)
class TaskNode:
    id: str
    agent: str
    objective: str
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
    request_summary: str = ""
    request_class: str = "general"
    issue_reference: str | None = None
    gates: tuple[str, ...] = ()
    forced_agents: tuple[str, ...] = ()
    decisions: tuple[AgentDecision, ...] = ()
    artifacts: tuple[ArtifactRequest, ...] = ()
    policy_version: int = 0
    trace: OrchestrationTrace | None = None

    @classmethod
    def from_json(cls, payload: str) -> "TaskPlan":
        cleaned = payload.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise TaskPlanError("Triage did not return valid JSON.") from exc

        if not isinstance(data, dict):
            raise TaskPlanError("Task plan root must be a JSON object.")

        raw_nodes = data.get("nodes") or []
        if not isinstance(raw_nodes, list):
            raise TaskPlanError("'nodes' must be a list.")

        nodes: list[TaskNode] = []
        for item in raw_nodes:
            if not isinstance(item, dict):
                raise TaskPlanError("Each task node must be an object.")
            nodes.append(
                TaskNode(
                    id=str(item.get("id") or "").strip(),
                    agent=normalize_agent_key(
                        str(item.get("agent") or "")
                    ),
                    objective=str(item.get("objective") or "").strip(),
                    depends_on=tuple(
                        str(value).strip()
                        for value in (item.get("depends_on") or [])
                    ),
                )
            )

        required_disabled = tuple(
            normalize_agent_key(str(value))
            for value in (data.get("required_disabled_agents") or [])
        )

        gates_raw = data.get("gates") or []
        if not isinstance(gates_raw, list):
            raise TaskPlanError("'gates' must be a list.")
        gates = tuple(normalize_gate(str(value)) for value in gates_raw)

        forced_raw = data.get("forced_agents") or []
        if not isinstance(forced_raw, list):
            raise TaskPlanError("'forced_agents' must be a list.")
        forced_agents = tuple(
            normalize_agent_key(str(value)) for value in forced_raw
        )

        decisions_raw = data.get("decisions") or []
        if not isinstance(decisions_raw, list):
            raise TaskPlanError("'decisions' must be a list.")
        decisions: list[AgentDecision] = []
        for item in decisions_raw:
            if not isinstance(item, dict):
                raise TaskPlanError(
                    "Each orchestration decision must be an object."
                )
            try:
                decisions.append(
                    AgentDecision(
                        agent=normalize_agent_key(
                            str(item.get("agent") or "")
                        ),
                        selected=bool(item.get("selected")),
                        reason=str(item.get("reason") or "").strip(),
                    )
                )
            except OrchestrationPolicyError as exc:
                raise TaskPlanError(str(exc)) from exc

        artifacts_raw = data.get("artifacts") or []
        if not isinstance(artifacts_raw, list):
            raise TaskPlanError("'artifacts' must be a list.")
        artifacts: list[ArtifactRequest] = []
        for item in artifacts_raw:
            if not isinstance(item, dict):
                raise TaskPlanError(
                    "Each artifact request must be an object."
                )
            artifacts.append(
                ArtifactRequest(
                    kind=str(item.get("kind") or "").strip(),
                    action=str(item.get("action") or "update").strip(),
                )
            )

        request = str(data.get("request") or "").strip()
        request_summary = str(
            data.get("request_summary") or request
        ).strip()

        plan = cls(
            request=request,
            nodes=nodes,
            required_disabled_agents=required_disabled,
            notes=(
                str(data.get("notes")).strip()
                if data.get("notes") is not None
                else None
            ),
            request_summary=request_summary,
            request_class=str(
                data.get("request_class") or "general"
            ).strip(),
            issue_reference=(
                str(data.get("issue_reference")).strip()
                if data.get("issue_reference") is not None
                else None
            ),
            gates=gates,
            forced_agents=forced_agents,
            decisions=tuple(decisions),
            artifacts=tuple(artifacts),
            policy_version=int(data.get("policy_version") or 0),
        )
        plan.validate_structure()
        return plan

    def validate_structure(self) -> None:
        if not self.request:
            raise TaskPlanError("Task plan request cannot be empty.")
        if not self.request_summary:
            raise TaskPlanError("Task plan request_summary cannot be empty.")
        if len(self.request_summary) > 800:
            raise TaskPlanError(
                "Task plan request_summary must be concise (<= 800 chars)."
            )
        if not self.request_class:
            raise TaskPlanError("Task plan request_class cannot be empty.")

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

        self._validate_acyclic(by_id)

    def validate_policy(self, enabled_agents: Iterable[str]) -> None:
        """Enforce M-028 participation gates for policy-v1 plans."""

        if self.policy_version < 1:
            return

        try:
            validate_plan_policy(
                gates=self.gates,
                forced_agents=self.forced_agents,
                decisions=self.decisions,
                planned_agents=(node.agent for node in self.nodes),
                required_disabled_agents=self.required_disabled_agents,
                enabled_agents=enabled_agents,
            )
        except OrchestrationPolicyError as exc:
            raise TaskPlanError(str(exc)) from exc

        if self.artifacts:
            represented = {
                node.agent for node in self.nodes
            } | set(self.required_disabled_agents)
            if "documentation" not in represented:
                raise TaskPlanError(
                    "Requested durable artifact(s) require Documentation."
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


def normalize_agent_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def build_planning_prompt(
    request: str,
    *,
    enabled_agents: Iterable[str],
    available_agents: Iterable[str],
) -> str:
    enabled = tuple(normalize_agent_key(item) for item in enabled_agents)
    available = tuple(normalize_agent_key(item) for item in available_agents)
    disabled = tuple(item for item in available if item not in set(enabled))

    return f"""Planning-only operation. Do not hand off.

Analyze the user request and return the MINIMUM SUFFICIENT task DAG as JSON only.

User request:
{request}

Enabled agent keys:
{", ".join(enabled) or "(none)"}

Known but disabled agent keys:
{", ".join(disabled) or "(none)"}

Participation gates:
- product_definition -> product
- delivery_planning -> pmo
- architecture_change -> architecture
- ux_change -> ux_ui
- backend_change -> backend
- frontend_change -> frontend
- database_change -> database
- security_risk -> security
- testing_required -> testing
- review_required -> reviewer
- durable_documentation -> documentation
- devops_change -> devops
- performance_concern -> performance
- reliability_or_incident -> observability
- data_change -> data

Rules:
- Activate ONLY gates justified by this request.
- Each active gate maps to one specialist; each specialist gets at most one node.
- Do not add Product, Architecture, Testing, Security, Reviewer, Documentation, or any other specialist by habit.
- Testing is selected only when repeatable technical validation adds value.
- Security is selected only for a real security/privacy/compliance risk surface.
- Documentation is selected only for durable knowledge/artifacts or explicit user request.
- Reviewer is selected only when independent technical review is justified by risk/scope.
- forced_agents is only for an explicit user request to involve a named specialist outside the normal gate decision.
- Every selected specialist requires a concise observable reason.
- You may record plausible specialists considered but omitted with selected=false and a concise reason; do not enumerate irrelevant roles.
- Never substitute a disabled specialist. If required, add it to required_disabled_agents and omit its node.
- Each node objective must be self-contained because execution receives request_summary, not the full conversation.
- Create independent branches when work can proceed independently.
- Express ordering only through depends_on.
- Do not create a human-QA node; human QA happens after the DAG.
- request_summary must be concise and exclude conversational noise.
- artifacts contains only durable artifacts to create/update (for example functional_spec, technical_spec, adr, runbook). Any artifact requires Documentation.
- policy_version must be 1.

Return exactly this shape:
{{
  "policy_version": 1,
  "request": "...",
  "request_summary": "...",
  "request_class": "bug|feature|docs|incident|performance|deployment|other",
  "issue_reference": null,
  "gates": ["backend_change", "testing_required"],
  "forced_agents": [],
  "required_disabled_agents": [],
  "decisions": [
    {{"agent": "backend", "selected": true, "reason": "Changes server behavior."}},
    {{"agent": "architecture", "selected": false, "reason": "No structural impact."}}
  ],
  "artifacts": [],
  "notes": "...",
  "nodes": [
    {{
      "id": "backend",
      "agent": "backend",
      "objective": "Implement the requested server behavior.",
      "depends_on": []
    }}
  ]
}}
"""
