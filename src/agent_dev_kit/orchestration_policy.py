from dataclasses import dataclass
from typing import Iterable


GATE_AGENT_MAP: dict[str, str] = {
    "product_definition": "product",
    "delivery_planning": "pmo",
    "architecture_change": "architecture",
    "ux_change": "ux_ui",
    "backend_change": "backend",
    "frontend_change": "frontend",
    "database_change": "database",
    "security_risk": "security",
    "testing_required": "testing",
    "review_required": "reviewer",
    "durable_documentation": "documentation",
    "devops_change": "devops",
    "performance_concern": "performance",
    "reliability_or_incident": "observability",
    "data_change": "data",
}


class OrchestrationPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentDecision:
    agent: str
    selected: bool
    reason: str

    def __post_init__(self) -> None:
        if not self.agent.strip():
            raise OrchestrationPolicyError("Agent decision requires an agent.")
        if not self.reason.strip():
            raise OrchestrationPolicyError(
                f"Agent decision for '{self.agent}' requires a concise reason."
            )


def normalize_agent_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def normalize_gate(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def required_agents_for_gates(
    gates: Iterable[str],
    *,
    forced_agents: Iterable[str] = (),
) -> tuple[str, ...]:
    required: list[str] = []

    for raw_gate in gates:
        gate = normalize_gate(raw_gate)
        try:
            agent = GATE_AGENT_MAP[gate]
        except KeyError as exc:
            raise OrchestrationPolicyError(
                f"Unknown orchestration gate '{raw_gate}'."
            ) from exc
        if agent not in required:
            required.append(agent)

    for raw_agent in forced_agents:
        agent = normalize_agent_key(raw_agent)
        if agent == "triage":
            raise OrchestrationPolicyError(
                "Triage plans work but must not be an execution node."
            )
        if agent not in required:
            required.append(agent)

    return tuple(required)


def validate_plan_policy(
    *,
    gates: Iterable[str],
    forced_agents: Iterable[str],
    decisions: Iterable[AgentDecision],
    planned_agents: Iterable[str],
    required_disabled_agents: Iterable[str],
    enabled_agents: Iterable[str],
) -> None:
    """Validate a model-proposed DAG against deterministic participation gates."""

    enabled = {normalize_agent_key(item) for item in enabled_agents}
    planned = tuple(normalize_agent_key(item) for item in planned_agents)
    disabled_required = {
        normalize_agent_key(item) for item in required_disabled_agents
    }

    if "triage" in planned:
        raise OrchestrationPolicyError(
            "Triage cannot appear as an execution node."
        )

    if len(planned) != len(set(planned)):
        duplicates = sorted(
            item for item in set(planned) if planned.count(item) > 1
        )
        raise OrchestrationPolicyError(
            "One execution node per specialist is required; duplicate agent(s): "
            + ", ".join(duplicates)
        )

    required = set(
        required_agents_for_gates(
            gates,
            forced_agents=forced_agents,
        )
    )
    represented = set(planned) | disabled_required

    missing = sorted(required - represented)
    if missing:
        raise OrchestrationPolicyError(
            "Gate(s) require missing specialist(s): " + ", ".join(missing)
        )

    extra = sorted(represented - required)
    if extra:
        raise OrchestrationPolicyError(
            "Planned specialist(s) have no active gate or explicit user force: "
            + ", ".join(extra)
        )

    expected_disabled = {item for item in required if item not in enabled}
    if disabled_required != expected_disabled:
        missing_disabled = sorted(expected_disabled - disabled_required)
        unexpected_disabled = sorted(disabled_required - expected_disabled)
        details: list[str] = []
        if missing_disabled:
            details.append(
                "required disabled not declared: " + ", ".join(missing_disabled)
            )
        if unexpected_disabled:
            details.append(
                "unexpected disabled declarations: "
                + ", ".join(unexpected_disabled)
            )
        raise OrchestrationPolicyError("; ".join(details))

    decision_list = tuple(decisions)
    selected = {
        normalize_agent_key(item.agent)
        for item in decision_list
        if item.selected
    }
    if selected != represented:
        missing_decisions = sorted(represented - selected)
        extra_decisions = sorted(selected - represented)
        details = []
        if missing_decisions:
            details.append(
                "selected decision missing for: "
                + ", ".join(missing_decisions)
            )
        if extra_decisions:
            details.append(
                "selected decision has no node/gate: "
                + ", ".join(extra_decisions)
            )
        raise OrchestrationPolicyError("; ".join(details))

    seen: set[str] = set()
    for decision in decision_list:
        agent = normalize_agent_key(decision.agent)
        if agent in seen:
            raise OrchestrationPolicyError(
                f"Duplicate orchestration decision for '{agent}'."
            )
        seen.add(agent)

        if not decision.selected and agent in represented:
            raise OrchestrationPolicyError(
                f"Agent '{agent}' cannot be both omitted and represented."
            )
