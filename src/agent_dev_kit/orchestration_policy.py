from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence


class RiskFlag(StrEnum):
    FUNCTIONAL_AMBIGUITY = "functional_ambiguity"
    BACKLOG_COORDINATION = "backlog_coordination"
    CROSS_LAYER = "cross_layer"
    UX_CHANGE = "ux_change"
    BACKEND_CHANGE = "backend_change"
    FRONTEND_CHANGE = "frontend_change"
    PERSISTENCE_CHANGE = "persistence_change"
    SECURITY_SURFACE = "security_surface"
    BEHAVIOR_REGRESSION = "behavior_regression"
    TECHNICAL_REVIEW = "technical_review"
    DEPLOYMENT_CHANGE = "deployment_change"
    PERFORMANCE_RISK = "performance_risk"
    RUNTIME_RELIABILITY = "runtime_reliability"
    ANALYTICS_DATA = "analytics_data"
    AUTH_CHANGE = "auth_change"
    SCHEMA_CHANGE = "schema_change"
    PUBLIC_API_CHANGE = "public_api_change"
    SENSITIVE_DATA = "sensitive_data"


class TaskPhase(StrEnum):
    INTAKE = "intake"
    ANALYSIS = "analysis"
    DISCOVERY = "discovery"
    PLANNING = "planning"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    REVIEW = "review"
    DOCUMENTATION = "documentation"
    OPERATIONS = "operations"
    RELEASE = "release"


class DurableArtifact(StrEnum):
    FUNCTIONAL_SPEC = "functional_spec"
    TECHNICAL_SPEC = "technical_spec"
    ADR = "adr"
    RUNBOOK = "runbook"
    RELEASE_NOTES = "release_notes"
    PROJECT_DOCS = "project_docs"
    REGULATORY_DOC = "regulatory_doc"


KNOWN_AGENT_KEYS = frozenset(
    {
        "triage",
        "product",
        "pmo",
        "architecture",
        "ux_ui",
        "backend",
        "frontend",
        "database",
        "security",
        "testing",
        "reviewer",
        "documentation",
        "devops",
        "performance",
        "observability",
        "data",
    }
)

RISK_REQUIRED_AGENTS: dict[str, tuple[str, ...]] = {
    RiskFlag.FUNCTIONAL_AMBIGUITY.value: ("product",),
    RiskFlag.BACKLOG_COORDINATION.value: ("pmo",),
    RiskFlag.CROSS_LAYER.value: ("architecture",),
    RiskFlag.UX_CHANGE.value: ("ux_ui",),
    RiskFlag.BACKEND_CHANGE.value: ("backend",),
    RiskFlag.FRONTEND_CHANGE.value: ("frontend",),
    RiskFlag.PERSISTENCE_CHANGE.value: ("database",),
    RiskFlag.SECURITY_SURFACE.value: ("security",),
    RiskFlag.BEHAVIOR_REGRESSION.value: ("testing",),
    RiskFlag.TECHNICAL_REVIEW.value: ("reviewer",),
    RiskFlag.DEPLOYMENT_CHANGE.value: ("devops",),
    RiskFlag.PERFORMANCE_RISK.value: ("performance",),
    RiskFlag.RUNTIME_RELIABILITY.value: ("observability",),
    RiskFlag.ANALYTICS_DATA.value: ("data",),
    RiskFlag.AUTH_CHANGE.value: ("security",),
    RiskFlag.SCHEMA_CHANGE.value: ("database",),
    RiskFlag.PUBLIC_API_CHANGE.value: ("security", "testing"),
    RiskFlag.SENSITIVE_DATA.value: ("security",),
}

ARTIFACT_REQUIRED_AGENTS: dict[str, tuple[str, ...]] = {
    DurableArtifact.FUNCTIONAL_SPEC.value: ("product",),
    DurableArtifact.TECHNICAL_SPEC.value: ("architecture",),
    DurableArtifact.ADR.value: ("architecture",),
    DurableArtifact.RUNBOOK.value: ("devops",),
}


@dataclass(frozen=True, slots=True)
class ProjectRoutingPolicy:
    """Deterministic project routing rule that can only add requirements."""

    id: str
    any_risk_flags: tuple[str, ...]
    all_risk_flags: tuple[str, ...]
    require_agents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    activated_policy_ids: tuple[str, ...] = ()
    required_agents: tuple[str, ...] = ()


def normalize_key(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
    )


def _coerce_enum(value: str, enum_type: type[StrEnum], label: str) -> str:
    normalized = normalize_key(str(value))
    try:
        return enum_type(normalized).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(
            f"Unknown {label} '{value}'. Allowed values: {allowed}."
        ) from exc


def coerce_risk_flag(value: str) -> str:
    return _coerce_enum(value, RiskFlag, "risk flag")


def coerce_task_phase(value: str) -> str:
    return _coerce_enum(value, TaskPhase, "task phase")


def coerce_durable_artifact(value: str) -> str:
    return _coerce_enum(value, DurableArtifact, "durable artifact")


def validate_profile_contracts(
    *,
    risk_flags: Iterable[str],
    durable_artifacts: Iterable[str],
) -> None:
    for value in risk_flags:
        coerce_risk_flag(value)
    for value in durable_artifacts:
        coerce_durable_artifact(value)


def project_policies_from_mapping(
    data: Any,
) -> tuple[ProjectRoutingPolicy, ...]:
    if data is None:
        return ()
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        raise ValueError("'orchestration.policies' must be a list.")

    policies: list[ProjectRoutingPolicy] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(data):
        if not isinstance(raw, Mapping):
            raise ValueError(
                f"orchestration.policies[{index}] must be a mapping."
            )

        policy_id = normalize_key(str(raw.get("id") or ""))
        if not policy_id:
            raise ValueError(
                f"orchestration.policies[{index}].id is required."
            )
        if policy_id in seen_ids:
            raise ValueError(
                f"Duplicate orchestration policy id '{policy_id}'."
            )
        seen_ids.add(policy_id)

        unknown_keys = set(raw) - {"id", "when", "require_agents"}
        if unknown_keys:
            raise ValueError(
                f"Policy '{policy_id}' contains unsupported field(s): "
                + ", ".join(sorted(str(item) for item in unknown_keys))
            )

        when = raw.get("when") or {}
        if not isinstance(when, Mapping):
            raise ValueError(f"Policy '{policy_id}'.when must be a mapping.")
        unknown_when = set(when) - {"any_risk_flags", "all_risk_flags"}
        if unknown_when:
            raise ValueError(
                f"Policy '{policy_id}'.when contains unsupported field(s): "
                + ", ".join(sorted(str(item) for item in unknown_when))
            )

        any_risks = _coerce_list(
            when.get("any_risk_flags"),
            f"Policy '{policy_id}'.when.any_risk_flags",
            coerce_risk_flag,
        )
        all_risks = _coerce_list(
            when.get("all_risk_flags"),
            f"Policy '{policy_id}'.when.all_risk_flags",
            coerce_risk_flag,
        )
        if not any_risks and not all_risks:
            raise ValueError(
                f"Policy '{policy_id}' requires at least one structured "
                "risk condition."
            )

        required_agents = _coerce_agent_list(
            raw.get("require_agents"),
            f"Policy '{policy_id}'.require_agents",
        )
        if not required_agents:
            raise ValueError(
                f"Policy '{policy_id}' requires at least one require_agents entry."
            )

        policies.append(
            ProjectRoutingPolicy(
                id=policy_id,
                any_risk_flags=any_risks,
                all_risk_flags=all_risks,
                require_agents=required_agents,
            )
        )

    return tuple(policies)


def preclassify_request(request: str) -> tuple[str, ...]:
    """Detect critical routing risks without consulting Triage or a model."""

    text = " ".join(request.lower().split())
    detected: list[str] = []

    def add(*values: RiskFlag) -> None:
        for value in values:
            if value.value not in detected:
                detected.append(value.value)

    if _matches(
        text,
        r"\b(auth|authentication|authorization|authorisation|login|log in|oauth2?|jwt|password|permissions?|roles?|session)\b",
    ):
        add(RiskFlag.AUTH_CHANGE, RiskFlag.SECURITY_SURFACE)

    if _matches(
        text,
        r"\b(schema|database migration|db migration|migrat(?:e|ion)|table|column|index|ddl|dml|stored procedure|trigger)\b",
    ):
        add(RiskFlag.SCHEMA_CHANGE, RiskFlag.PERSISTENCE_CHANGE)

    if _matches(
        text,
        r"\b(ci/cd|cicd|deployment|deploy|github actions?|pipeline|docker|kubernetes|helm|terraform)\b",
    ):
        add(RiskFlag.DEPLOYMENT_CHANGE)

    if _matches(
        text,
        r"\b(public api|api endpoint|rest endpoint|endpoint|webhook|http route)\b",
    ):
        add(
            RiskFlag.PUBLIC_API_CHANGE,
            RiskFlag.BACKEND_CHANGE,
            RiskFlag.SECURITY_SURFACE,
        )

    if _matches(
        text,
        r"\b(pii|personal data|sensitive data|credentials?|api key|access token|refresh token|secret)\b",
    ):
        add(RiskFlag.SENSITIVE_DATA, RiskFlag.SECURITY_SURFACE)

    return tuple(detected)


def evaluate_project_policies(
    risk_flags: Iterable[str],
    policies: Iterable[ProjectRoutingPolicy],
) -> PolicyEvaluation:
    known_risks = {coerce_risk_flag(value) for value in risk_flags}
    activated: list[str] = []
    required: list[str] = []

    for policy in policies:
        any_match = (
            not policy.any_risk_flags
            or bool(known_risks.intersection(policy.any_risk_flags))
        )
        all_match = set(policy.all_risk_flags).issubset(known_risks)
        if not (any_match and all_match):
            continue
        activated.append(policy.id)
        for agent in policy.require_agents:
            if agent not in required:
                required.append(agent)

    return PolicyEvaluation(
        activated_policy_ids=tuple(activated),
        required_agents=tuple(required),
    )


def _coerce_list(
    value: Any,
    label: str,
    coercer,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a list.")
    result: list[str] = []
    for item in value:
        coerced = coercer(str(item))
        if coerced not in result:
            result.append(coerced)
    return tuple(result)


def _coerce_agent_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a list.")
    result: list[str] = []
    for item in value:
        agent = normalize_key(str(item))
        if agent not in KNOWN_AGENT_KEYS or agent == "triage":
            raise ValueError(
                f"Unknown or unsupported required agent '{item}' in {label}."
            )
        if agent not in result:
            result.append(agent)
    return tuple(result)


def _matches(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None
