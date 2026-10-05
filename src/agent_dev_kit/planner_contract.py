from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from agent_dev_kit.orchestration_policy import (
    DurableArtifact,
    RiskFlag,
    TaskPhase,
)


@dataclass(frozen=True, slots=True)
class PlannerRequestProfile:
    summary: str
    classification: str
    risk_flags: list[RiskFlag]
    durable_artifacts: list[DurableArtifact]


@dataclass(frozen=True, slots=True)
class PlannerAgentDecision:
    agent: str
    selected: bool
    gate: str
    reason: str


@dataclass(frozen=True, slots=True)
class PlannerTaskNode:
    id: str
    agent: str
    phase: TaskPhase
    objective: str
    depends_on: list[str]


@dataclass(frozen=True, slots=True)
class StructuredTaskPlan:
    """Provider-facing structured output contract for planning."""

    request: str
    profile: PlannerRequestProfile
    agent_decisions: list[PlannerAgentDecision]
    required_disabled_agents: list[str]
    notes: str | None
    nodes: list[PlannerTaskNode]

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


def planner_payload_to_mapping(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, StructuredTaskPlan):
        return payload.to_mapping()
    if isinstance(payload, Mapping):
        return payload
    raise TypeError(
        "Planner output must be StructuredTaskPlan or a mapping."
    )
