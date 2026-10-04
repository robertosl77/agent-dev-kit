import json
from dataclasses import dataclass, field
from typing import Any, Iterable


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

        plan = cls(
            request=str(data.get("request") or "").strip(),
            nodes=nodes,
            required_disabled_agents=required_disabled,
            notes=(
                str(data.get("notes")).strip()
                if data.get("notes") is not None
                else None
            ),
        )
        plan.validate_structure()
        return plan

    def validate_structure(self) -> None:
        if not self.request:
            raise TaskPlanError("Task plan request cannot be empty.")

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

Analyze the user request and return a task execution DAG as JSON only.

User request:
{request}

Enabled agent keys:
{", ".join(enabled) or "(none)"}

Known but disabled agent keys:
{", ".join(disabled) or "(none)"}

Rules:
- Use responsibilities, not technologies, to choose agents.
- Never substitute a disabled specialist with another agent.
- If a disabled specialist is required, add its key to
  required_disabled_agents and do not assign its work to another role.
- Create independent branches when work can proceed independently.
- Express ordering only through depends_on.
- Prefer direct specialist-to-specialist flow when the dependency is clear.
- Include testing and reviewer when technical changes require validation,
  if those agents are enabled.
- Include documentation for durable work when documentation is enabled.
- Do not create a human-QA node; human QA happens after the DAG.
- Keep nodes cohesive and avoid duplicate responsibility.

Return exactly this shape:
{{
  "request": "...",
  "required_disabled_agents": ["ux_ui"],
  "notes": "...",
  "nodes": [
    {{
      "id": "architecture",
      "agent": "architecture",
      "objective": "...",
      "depends_on": []
    }}
  ]
}}
"""
