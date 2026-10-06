"""Token usage per model call and per run (M-036).

Every provider reports what its API returned (input/output tokens and, when
available, reasoning and cached tokens). Cost is only estimated when the
consuming project declares prices in ``project.yaml`` (``pricing``): Agent Dev
Kit does not keep a price list of its own, so nothing goes stale silently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(slots=True)
class UsageRecord:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0
    requests: int = 1

    def add(self, other: "UsageRecord") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.requests += other.requests

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD per million tokens, as declared by the consuming project."""

    input_per_mtok: float
    output_per_mtok: float


def merge_usage(records: Iterable[UsageRecord]) -> list[UsageRecord]:
    """One record per provider+model."""

    merged: dict[tuple[str, str], UsageRecord] = {}
    for record in records:
        key = (record.provider, record.model)
        if key in merged:
            merged[key].add(record)
        else:
            merged[key] = UsageRecord(**record.to_dict())
    return list(merged.values())


def total_tokens(records: Iterable[Mapping[str, Any] | UsageRecord]) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "requests": 0}
    for record in records:
        data = record.to_dict() if isinstance(record, UsageRecord) else record
        for key in totals:
            totals[key] += int(data.get(key) or 0)
    return totals


def estimate_cost(
    records: Iterable[Mapping[str, Any] | UsageRecord],
    pricing: Mapping[str, ModelPrice],
) -> float | None:
    """USD estimate, or None when any model used has no declared price."""

    total = 0.0
    seen = False
    for record in records:
        data = record.to_dict() if isinstance(record, UsageRecord) else record
        price = pricing.get(str(data.get("model") or ""))
        if price is None:
            return None
        seen = True
        total += int(data.get("input_tokens") or 0) * price.input_per_mtok / 1_000_000
        total += int(data.get("output_tokens") or 0) * price.output_per_mtok / 1_000_000
    return total if seen else None


def format_usage_line(
    stages: Iterable[tuple[str, Iterable[Mapping[str, Any] | UsageRecord]]],
    pricing: Mapping[str, ModelPrice] | None = None,
) -> str:
    """``consumo: planner 9.800 in / 1.900 out · doc-1 ... · total ...``"""

    parts: list[str] = []
    everything: list[Mapping[str, Any] | UsageRecord] = []
    models: set[str] = set()
    for label, records in stages:
        records = list(records)
        if not records:
            continue
        everything.extend(records)
        totals = total_tokens(records)
        parts.append(
            f"{label} {_n(totals['input_tokens'])} in / {_n(totals['output_tokens'])} out"
        )
        for record in records:
            data = record.to_dict() if isinstance(record, UsageRecord) else record
            models.add(str(data.get("model") or "?"))

    if not everything:
        return "consumo: sin datos del proveedor"

    totals = total_tokens(everything)
    summary = (
        f"total {_n(totals['input_tokens'])} in / {_n(totals['output_tokens'])} out"
    )
    cost = estimate_cost(everything, pricing or {})
    if cost is not None:
        summary += f" ≈ USD {cost:.4f}".replace(".", ",")
    summary += f" ({', '.join(sorted(models))})"
    return "consumo: " + " · ".join(parts + [summary])


def _n(value: int) -> str:
    return f"{value:,}".replace(",", ".")
