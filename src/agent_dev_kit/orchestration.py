from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


AGENT_GATE_GUIDANCE: dict[str, str] = {
    "product": (
        "Select only for new/changed functional intent, business rules, "
        "acceptance criteria, product discovery, or unresolved requirements."
    ),
    "pmo": (
        "Select only for backlog governance, sequencing, dependencies, "
        "release planning, blockers, or work-management decisions."
    ),
    "architecture": (
        "Select only for cross-layer impact, ownership/boundary decisions, "
        "new integrations, structural refactors, or durable technical design."
    ),
    "ux_ui": (
        "Select only for user flows, interaction behavior, accessibility, "
        "responsive behavior, or non-trivial interface/design decisions."
    ),
    "backend": (
        "Select when server-side/application-service behavior must change."
    ),
    "frontend": (
        "Select when client-side/UI implementation must change."
    ),
    "database": (
        "Select for operational persistence, schema, migration, query, index, "
        "transaction, trigger, or database-owned behavior."
    ),
    "security": (
        "Select when material security/privacy attack surface exists: auth, "
        "permissions, untrusted input, sensitive data, uploads, persistence "
        "queries, secrets, exposed configuration, dependencies, or trust "
        "boundaries."
    ),
    "testing": (
        "Select when changed behavior, regression risk, business logic, API "
        "contracts, integrations, edge cases, or defined security/accessibility "
        "checks justify repeatable technical validation. Do not select for "
        "pure documentation or truly trivial no-behavior changes."
    ),
    "reviewer": (
        "Select for independent technical review when risk, scope, multiple "
        "components, security findings, or non-trivial behavior justify it. "
        "A tiny low-risk change may use a simplified path."
    ),
    "documentation": (
        "Select only when durable knowledge must be created/updated or the user "
        "explicitly requests a document. Do not select merely to narrate every "
        "subtask; Issue/PR evidence is enough for transient implementation detail."
    ),
    "devops": (
        "Select for CI/CD, environments, deployment, releases, infrastructure, "
        "operational packaging, or delivery-pipeline controls."
    ),
    "performance": (
        "Select only for measurable latency/throughput/resource/query/model-cost "
        "concerns or performance regression."
    ),
    "observability": (
        "Select for runtime telemetry, SLI/SLO, health, alerting, incident "
        "diagnosis, or reliability visibility."
    ),
    "data": (
        "Select for ETL/ELT, analytical/reporting datasets, data movement, "
        "lineage, or analytical quality."
    ),
}


RISK_REQUIRED_AGENT: dict[str, str] = {
    "functional_ambiguity": "product",
    "backlog_coordination": "pmo",
    "cross_layer": "architecture",
    "ux_change": "ux_ui",
    "backend_change": "backend",
    "frontend_change": "frontend",
    "persistence_change": "database",
    "security_surface": "security",
    "behavior_regression": "testing",
    "technical_review": "reviewer",
    "deployment_change": "devops",
    "performance_risk": "performance",
    "runtime_reliability": "observability",
    "analytics_data": "data",
}


ARTIFACT_REQUIRED_AGENT: dict[str, str] = {
    "functional_spec": "product",
    "technical_spec": "architecture",
    "adr": "architecture",
    "runbook": "devops",
}


@dataclass(frozen=True, slots=True)
class AgentGateDecision:
    agent: str
    selected: bool
    gate: str
    reason: str


@dataclass(frozen=True, slots=True)
class RequestProfile:
    summary: str
    classification: str
    risk_flags: tuple[str, ...] = ()
    durable_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OrchestrationConfig:
    trace_enabled: bool = True
    trace_path: str = ".agent-dev-kit/runtime/orchestration-traces.jsonl"
    persist_full_request: bool = False
    improvement_candidate_threshold: int = 3
    document_templates: Mapping[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class OrchestrationTrace:
    request_summary: str
    request_fingerprint: str
    classification: str
    risk_flags: tuple[str, ...]
    durable_artifacts: tuple[str, ...]
    agent_decisions: tuple[AgentGateDecision, ...]
    dag: tuple[dict[str, Any], ...]
    routing_fingerprint: str = ""
    full_request: str | None = None
    model_calls: int = 0
    handoffs: int = 0
    revisits: int = 0
    node_attempts: dict[str, int] = field(default_factory=dict)
    node_durations_ms: dict[str, float] = field(default_factory=dict)
    status: str = "planned"
    human_overrides: list[str] = field(default_factory=list)
    persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_summary": self.request_summary,
            "request_fingerprint": self.request_fingerprint,
            "classification": self.classification,
            "routing_fingerprint": self.routing_fingerprint,
            "risk_flags": list(self.risk_flags),
            "durable_artifacts": list(self.durable_artifacts),
            "agent_decisions": [asdict(item) for item in self.agent_decisions],
            "dag": list(self.dag),
            "full_request": self.full_request,
            "model_calls": self.model_calls,
            "handoffs": self.handoffs,
            "revisits": self.revisits,
            "node_attempts": dict(self.node_attempts),
            "node_durations_ms": dict(self.node_durations_ms),
            "status": self.status,
            "human_overrides": list(self.human_overrides),
        }


@dataclass(frozen=True, slots=True)
class OrchestrationImprovementCandidate:
    kind: str
    classification: str
    evidence_count: int
    message: str


class OrchestrationTraceStore:
    """Append-only local JSONL trace storage. Raw traces are not Git history."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, trace: OrchestrationTrace) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    trace.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
        trace.persisted = True

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                cleaned = line.strip()
                if cleaned:
                    rows.append(json.loads(cleaned))
        return rows


def orchestration_config_from_mapping(
    data: Mapping[str, Any] | None,
) -> OrchestrationConfig:
    if not data:
        return OrchestrationConfig()
    if not isinstance(data, Mapping):
        raise ValueError("'orchestration' must be a mapping.")

    trace = data.get("trace") or {}
    if not isinstance(trace, Mapping):
        raise ValueError("'orchestration.trace' must be a mapping.")

    templates = data.get("document_templates") or {}
    if not isinstance(templates, Mapping):
        raise ValueError(
            "'orchestration.document_templates' must be a mapping."
        )

    threshold = int(data.get("improvement_candidate_threshold", 3))
    if threshold < 2:
        raise ValueError(
            "orchestration.improvement_candidate_threshold must be >= 2."
        )

    return OrchestrationConfig(
        trace_enabled=bool(trace.get("enabled", True)),
        trace_path=str(
            trace.get(
                "path",
                ".agent-dev-kit/runtime/orchestration-traces.jsonl",
            )
        ).strip(),
        persist_full_request=bool(
            trace.get("persist_full_request", False)
        ),
        improvement_candidate_threshold=threshold,
        document_templates={
            str(key).strip(): str(value).strip()
            for key, value in templates.items()
            if str(key).strip() and str(value).strip()
        },
    )


def fingerprint_request(request: str, classification: str = "") -> str:
    normalized = " ".join(request.lower().split())
    payload = f"{classification.strip().lower()}|{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]


def fingerprint_routing(profile: RequestProfile) -> str:
    payload = "|".join(
        (
            profile.classification.strip().lower(),
            ",".join(sorted(profile.risk_flags)),
            ",".join(sorted(profile.durable_artifacts)),
        )
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]


def validate_gate_policy(
    *,
    profile: RequestProfile,
    decisions: Iterable[AgentGateDecision],
    enabled_agents: Iterable[str],
    required_disabled_agents: Iterable[str] = (),
) -> None:
    enabled = {normalize_agent_key(value) for value in enabled_agents}
    required_disabled = {
        normalize_agent_key(value) for value in required_disabled_agents
    }
    by_agent = {
        normalize_agent_key(item.agent): item
        for item in decisions
    }

    for risk in profile.risk_flags:
        agent = RISK_REQUIRED_AGENT.get(risk)
        if not agent:
            continue
        if agent not in enabled:
            if agent not in required_disabled:
                raise ValueError(
                    f"Risk '{risk}' requires disabled agent '{agent}', "
                    "which must be declared in required_disabled_agents."
                )
            continue
        decision = by_agent.get(agent)
        if decision is None or not decision.selected:
            raise ValueError(
                f"Risk '{risk}' requires selected agent '{agent}'."
            )

    for artifact in profile.durable_artifacts:
        agent = ARTIFACT_REQUIRED_AGENT.get(artifact)
        if agent:
            if agent not in enabled:
                if agent not in required_disabled:
                    raise ValueError(
                        f"Artifact '{artifact}' requires disabled agent "
                        f"'{agent}', which must be declared in "
                        "required_disabled_agents."
                    )
            else:
                decision = by_agent.get(agent)
                if decision is None or not decision.selected:
                    raise ValueError(
                        f"Artifact '{artifact}' requires selected agent "
                        f"'{agent}'."
                    )

    if profile.durable_artifacts:
        if "documentation" not in enabled:
            if "documentation" not in required_disabled:
                raise ValueError(
                    "Durable artifacts require disabled agent "
                    "'documentation', which must be declared in "
                    "required_disabled_agents."
                )
        else:
            decision = by_agent.get("documentation")
            if decision is None or not decision.selected:
                raise ValueError(
                    "Durable artifacts require Agent Documentation for "
                    "consolidation/synchronization."
                )


def detect_improvement_candidates(
    traces: Iterable[Mapping[str, Any]],
    *,
    threshold: int = 3,
) -> tuple[OrchestrationImprovementCandidate, ...]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for trace in traces:
        key = (
            str(
                trace.get("routing_fingerprint")
                or trace.get("request_fingerprint")
                or ""
            ),
            str(trace.get("classification") or ""),
        )
        grouped.setdefault(key, []).append(trace)

    candidates: list[OrchestrationImprovementCandidate] = []
    for (_, classification), items in grouped.items():
        if len(items) < threshold:
            continue

        selected_sets = {
            tuple(
                sorted(
                    decision["agent"]
                    for decision in item.get("agent_decisions", [])
                    if decision.get("selected")
                )
            )
            for item in items
        }
        if len(selected_sets) > 1:
            candidates.append(
                OrchestrationImprovementCandidate(
                    kind="inconsistent_routing",
                    classification=classification,
                    evidence_count=len(items),
                    message=(
                        "Equivalent requests produced different specialist "
                        "subgraphs. Review gate consistency."
                    ),
                )
            )

        revisits = sum(int(item.get("revisits") or 0) for item in items)
        if revisits >= threshold:
            candidates.append(
                OrchestrationImprovementCandidate(
                    kind="repeated_revisits",
                    classification=classification,
                    evidence_count=len(items),
                    message=(
                        "Equivalent requests repeatedly revisited nodes. "
                        "Review dependencies, exit conditions, and context."
                    ),
                )
            )

    return tuple(candidates)


def normalize_agent_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
