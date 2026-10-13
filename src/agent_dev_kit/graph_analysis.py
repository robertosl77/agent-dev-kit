"""Read the per-run graph log and look for routing improvements (M-068).

Every /plan, /task and /do appends one record to
``.agent-dev-kit/runtime/orchestration-traces.jsonl`` with the graph, Triage's
decisions, the model, token usage and tool events. This module only reads
that log: it proposes, it never changes the routing (human review).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from agent_dev_kit.orchestration import (
    OrchestrationImprovementCandidate,
    detect_improvement_candidates,
)
from agent_dev_kit.usage import _n, total_tokens


@dataclass(frozen=True, slots=True)
class GraphRow:
    recorded_at: str
    mode: str
    status: str
    classification: str
    model: str
    agents: tuple[str, ...]
    nodes: int
    input_tokens: int
    output_tokens: int
    planner_input_tokens: int


def graph_rows(traces: Iterable[Mapping[str, Any]]) -> list[GraphRow]:
    rows: dict[str, GraphRow] = {}
    order: list[str] = []
    for trace in traces:
        # Each run may be persisted more than once (planned → completed).
        key = str(trace.get("run_id") or "") or "|".join(
            (
                str(trace.get("recorded_at") or ""),
                str(trace.get("request_fingerprint") or ""),
            )
        )
        usage = trace.get("usage") or []
        totals = total_tokens(usage)
        planner = total_tokens(item for item in usage if item.get("stage") == "planner")
        row = GraphRow(
            recorded_at=str(trace.get("recorded_at") or "-"),
            mode=str(trace.get("mode") or "-"),
            status=str(trace.get("status") or "-"),
            classification=str(trace.get("classification") or "-"),
            model=str(trace.get("model") or "-"),
            agents=tuple(sorted({str(node.get("agent")) for node in trace.get("dag") or []})),
            nodes=len(trace.get("dag") or []),
            input_tokens=totals["input_tokens"],
            output_tokens=totals["output_tokens"],
            planner_input_tokens=planner["input_tokens"],
        )
        if key not in rows:
            order.append(key)
        rows[key] = row
    return [rows[key] for key in order]


def intake_candidates(
    traces: Iterable[Mapping[str, Any]],
    *,
    threshold: int,
) -> list[OrchestrationImprovementCandidate]:
    """Same deterministic intake (risks + enabled agents), different Triage output."""

    groups: dict[str, list[Mapping[str, Any]]] = {}
    for trace in traces:
        key = str(trace.get("intake_key") or "")
        if key:
            groups.setdefault(key, []).append(trace)

    candidates = []
    for items in groups.values():
        if len(items) < threshold:
            continue
        classifications = {str(item.get("classification") or "") for item in items}
        if len(classifications) > 1:
            candidates.append(
                OrchestrationImprovementCandidate(
                    kind="inconsistent_classification",
                    classification=", ".join(sorted(classifications)),
                    evidence_count=len(items),
                    message=(
                        "Requests with the same deterministic risk profile were "
                        "classified differently by Triage. Review the Triage "
                        "instructions or add a project policy."
                    ),
                )
            )
    return candidates


def analysis_report(
    traces: list[Mapping[str, Any]],
    *,
    threshold: int,
) -> list[str]:
    rows = graph_rows(traces)
    completed = [row for row in rows if row.status in {"completed", "planned_only"}]
    lines = [f"Usos registrados: {len(rows)}"]
    if not rows:
        return lines + ["Todavía no hay grafos registrados en este proyecto."]

    agent_counts = Counter(agent for row in rows for agent in row.agents)
    lines.append(
        "Agentes más convocados: "
        + ", ".join(f"{agent} ×{count}" for agent, count in agent_counts.most_common(8))
    )
    total_in = sum(row.input_tokens for row in rows)
    planner_in = sum(row.planner_input_tokens for row in rows)
    if total_in:
        lines.append(
            f"Tokens de entrada: {total_in:,} en total; la planificación (Triage) "
            f"representa el {planner_in * 100 // total_in}%.".replace(",", ".")
        )
    if completed:
        average = sum(row.nodes for row in completed) / len(completed)
        lines.append(f"Promedio de nodos por grafo: {average:.1f}".replace(".", ","))

    candidates = list(detect_improvement_candidates(traces, threshold=threshold))
    candidates += intake_candidates(traces, threshold=threshold)
    if not candidates:
        lines.append(
            "Sin candidatos de mejora: los usos equivalentes armaron grafos "
            f"consistentes (se comparan grupos de al menos {threshold} usos)."
        )
    else:
        lines.append("Candidatos de mejora (para revisión humana, no se aplican solos):")
        for candidate in candidates:
            lines.append(
                f"  - [{candidate.kind}] {candidate.classification} "
                f"({candidate.evidence_count} usos): {candidate.message}"
            )
    return lines


def format_graph_rows(rows: list[GraphRow]) -> list[str]:
    if not rows:
        return ["Todavía no hay grafos registrados en este proyecto."]
    lines = []
    for row in rows:
        lines.append(
            f"{row.recorded_at[:16]} · {row.mode:<7} · {row.status:<12} · "
            f"{row.classification} · {row.nodes} nodo(s): {', '.join(row.agents) or '-'} · "
            f"{_n(row.input_tokens)} in / {_n(row.output_tokens)} out · {row.model}"
        )
    return lines
