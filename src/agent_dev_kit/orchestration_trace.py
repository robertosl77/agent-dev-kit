from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from agent_dev_kit.orchestration_policy import AgentDecision


@dataclass(slots=True)
class TraceCall:
    stage: str
    agent: str
    phase: str
    provider: str
    duration_ms: int
    context_chars: int
    status: str = "completed"
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "agent": self.agent,
            "phase": self.phase,
            "provider": self.provider,
            "duration_ms": self.duration_ms,
            "context_chars": self.context_chars,
            "status": self.status,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "error_type": self.error_type,
        }


@dataclass(slots=True)
class OrchestrationTrace:
    request_summary: str
    request_class: str
    request_fingerprint: str
    gates: tuple[str, ...]
    selected_agents: tuple[str, ...]
    considered_omitted: tuple[tuple[str, str], ...] = ()
    issue_reference: str | None = None
    raw_request: str | None = None
    trace_id: str = field(default_factory=lambda: f"trace_{uuid4().hex}")
    started_at: str = field(default_factory=lambda: _utc_now())
    finished_at: str | None = None
    status: str = "planned"
    qa_status: str = "pending"
    calls: list[TraceCall] = field(default_factory=list)
    human_overrides: list[str] = field(default_factory=list)
    dag: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        request: str,
        request_summary: str,
        request_class: str,
        gates: Iterable[str],
        decisions: Iterable[AgentDecision],
        dag: Iterable[dict[str, Any]],
        issue_reference: str | None = None,
        retain_request_text: bool = False,
    ) -> "OrchestrationTrace":
        decision_list = tuple(decisions)
        selected = tuple(
            item.agent for item in decision_list if item.selected
        )
        omitted = tuple(
            (item.agent, item.reason)
            for item in decision_list
            if not item.selected
        )
        return cls(
            request_summary=request_summary.strip(),
            request_class=request_class.strip(),
            request_fingerprint=fingerprint_request(request),
            gates=tuple(gates),
            selected_agents=selected,
            considered_omitted=omitted,
            issue_reference=issue_reference,
            raw_request=request if retain_request_text else None,
            dag=[dict(item) for item in dag],
        )

    @property
    def provider_calls(self) -> int:
        return len(self.calls)

    @property
    def revisits(self) -> int:
        seen: set[tuple[str, str]] = set()
        repeated = 0
        for call in self.calls:
            if call.stage != "execution":
                continue
            key = (call.agent, call.phase)
            if key in seen:
                repeated += 1
            else:
                seen.add(key)
        return repeated

    @property
    def total_context_chars(self) -> int:
        return sum(item.context_chars for item in self.calls)

    @property
    def total_tokens(self) -> int | None:
        values = [
            item.total_tokens
            for item in self.calls
            if item.total_tokens is not None
        ]
        if not values:
            return None
        return sum(values)

    def record_call(
        self,
        *,
        stage: str,
        agent: str,
        provider: str,
        duration_ms: int,
        phase: str = "work",
        context_chars: int,
        native_result: Any | None = None,
        status: str = "completed",
        error_type: str | None = None,
    ) -> None:
        usage = extract_usage(native_result)
        self.calls.append(
            TraceCall(
                stage=stage,
                agent=agent,
                phase=phase,
                provider=provider,
                duration_ms=max(0, int(duration_ms)),
                context_chars=max(0, int(context_chars)),
                status=status,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
                error_type=error_type,
            )
        )

    def finish(self, status: str = "completed") -> None:
        self.status = status
        self.finished_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_summary": self.request_summary,
            "request_fingerprint": self.request_fingerprint,
            "request_class": self.request_class,
            "issue_reference": self.issue_reference,
            "gates": list(self.gates),
            "selected_agents": list(self.selected_agents),
            "considered_omitted": [
                {"agent": agent, "reason": reason}
                for agent, reason in self.considered_omitted
            ],
            "dag": [dict(item) for item in self.dag],
            "status": self.status,
            "qa_status": self.qa_status,
            "provider_calls": self.provider_calls,
            "revisits": self.revisits,
            "total_context_chars": self.total_context_chars,
            "total_tokens": self.total_tokens,
            "human_overrides": list(self.human_overrides),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "calls": [item.to_dict() for item in self.calls],
            **(
                {"raw_request": self.raw_request}
                if self.raw_request is not None
                else {}
            ),
        }


@dataclass(frozen=True, slots=True)
class IssueProposal:
    title: str
    body: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "evidence": list(self.evidence),
        }


class JsonlTraceStore:
    """Optional local persistence for structured orchestration traces."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, trace: OrchestrationTrace) -> None:
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


def fingerprint_request(request: str) -> str:
    normalized = " ".join(request.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_usage(native_result: Any | None) -> dict[str, int | None]:
    if native_result is None:
        return {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }

    candidates = [
        getattr(native_result, "usage", None),
        getattr(
            getattr(native_result, "context_wrapper", None),
            "usage",
            None,
        ),
    ]

    for usage in candidates:
        if usage is None:
            continue

        input_tokens = _usage_value(
            usage,
            "input_tokens",
            "prompt_tokens",
        )
        output_tokens = _usage_value(
            usage,
            "output_tokens",
            "completion_tokens",
        )
        total_tokens = _usage_value(usage, "total_tokens")

        if total_tokens is None and (
            input_tokens is not None or output_tokens is not None
        ):
            total_tokens = (input_tokens or 0) + (output_tokens or 0)

        if (
            input_tokens is not None
            or output_tokens is not None
            or total_tokens is not None
        ):
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }

    return {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }


def suggest_trace_review_issues(
    traces: Iterable[OrchestrationTrace],
    *,
    min_occurrences: int = 3,
) -> tuple[IssueProposal, ...]:
    """Create human-review proposals from objective repeated trace signals.

    This never changes orchestration policy and never creates a GitHub Issue.
    A caller may submit the proposal through an explicitly authorized tool.
    """

    if min_occurrences < 1:
        raise ValueError("min_occurrences must be >= 1.")

    grouped: dict[str, list[OrchestrationTrace]] = {}
    for trace in traces:
        grouped.setdefault(trace.request_class, []).append(trace)

    proposals: list[IssueProposal] = []

    for request_class, group in sorted(grouped.items()):
        revisit_traces = [item for item in group if item.revisits > 0]
        if len(revisit_traces) >= min_occurrences:
            evidence = tuple(item.trace_id for item in revisit_traces)
            proposals.append(
                IssueProposal(
                    title=(
                        "Orchestration review — repeated specialist revisits "
                        f"for {request_class}"
                    ),
                    body=(
                        "Structured traces repeatedly show execution revisits "
                        f"for request class '{request_class}'. Review gates, "
                        "node boundaries, and handoff context before changing "
                        "policy. No automatic policy change is authorized."
                    ),
                    evidence=evidence,
                )
            )

        failed = [
            item
            for item in group
            if item.status in {"failed", "blocked"}
        ]
        if len(failed) >= min_occurrences:
            evidence = tuple(item.trace_id for item in failed)
            proposals.append(
                IssueProposal(
                    title=(
                        "Orchestration review — repeated blocked/failed "
                        f"{request_class} tasks"
                    ),
                    body=(
                        "Structured traces repeatedly show blocked or failed "
                        f"tasks for request class '{request_class}'. Review "
                        "routing/gates and execution evidence. No automatic "
                        "framework modification is authorized."
                    ),
                    evidence=evidence,
                )
            )

    return tuple(proposals)


def _usage_value(usage: Any, *names: str) -> int | None:
    for name in names:
        if isinstance(usage, dict) and name in usage:
            value = usage[name]
        else:
            value = getattr(usage, name, None)

        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
