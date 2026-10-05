from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class OrchestrationBudgetConfig:
    """Hard execution budgets for one task orchestration."""

    max_dag_nodes: int = 12
    max_provider_calls: int = 24
    max_revisits: int = 2
    max_context_chars: int = 16000
    max_dependency_evidence_chars: int = 8000


class OrchestrationBudgetExceeded(RuntimeError):
    """Raised when continuing a task would exceed a hard orchestration budget."""

    status = "requires_human_approval"

    def __init__(
        self,
        *,
        budget: str,
        limit: int,
        actual: int,
        stage: str,
        message: str | None = None,
    ) -> None:
        self.budget = budget
        self.limit = limit
        self.actual = actual
        self.stage = stage
        detail = message or (
            f"Orchestration budget '{budget}' exceeded during {stage}: "
            f"limit={limit}, actual={actual}."
        )
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": "budget_exceeded",
            "budget": self.budget,
            "limit": self.limit,
            "actual": self.actual,
            "stage": self.stage,
            "message": str(self),
        }


def orchestration_budget_from_mapping(
    data: Mapping[str, Any] | None,
) -> OrchestrationBudgetConfig:
    if data is None:
        return OrchestrationBudgetConfig()
    if not isinstance(data, Mapping):
        raise ValueError("'orchestration.budgets' must be a mapping.")

    allowed = {
        "max_dag_nodes",
        "max_provider_calls",
        "max_revisits",
        "max_context_chars",
        "max_dependency_evidence_chars",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            "Unknown orchestration budget field(s): "
            + ", ".join(sorted(str(value) for value in unknown))
        )

    defaults = OrchestrationBudgetConfig()
    values = {
        "max_dag_nodes": _positive_int(
            data.get("max_dag_nodes", defaults.max_dag_nodes),
            "orchestration.budgets.max_dag_nodes",
        ),
        "max_provider_calls": _positive_int(
            data.get("max_provider_calls", defaults.max_provider_calls),
            "orchestration.budgets.max_provider_calls",
        ),
        "max_revisits": _non_negative_int(
            data.get("max_revisits", defaults.max_revisits),
            "orchestration.budgets.max_revisits",
        ),
        "max_context_chars": _positive_int(
            data.get("max_context_chars", defaults.max_context_chars),
            "orchestration.budgets.max_context_chars",
        ),
        "max_dependency_evidence_chars": _non_negative_int(
            data.get(
                "max_dependency_evidence_chars",
                defaults.max_dependency_evidence_chars,
            ),
            "orchestration.budgets.max_dependency_evidence_chars",
        ),
    }

    if values["max_dependency_evidence_chars"] > values["max_context_chars"]:
        raise ValueError(
            "orchestration.budgets.max_dependency_evidence_chars "
            "cannot exceed max_context_chars."
        )

    return OrchestrationBudgetConfig(**values)


def _positive_int(value: Any, label: str) -> int:
    parsed = _parse_int(value, label)
    if parsed <= 0:
        raise ValueError(f"{label} must be > 0.")
    return parsed


def _non_negative_int(value: Any, label: str) -> int:
    parsed = _parse_int(value, label)
    if parsed < 0:
        raise ValueError(f"{label} must be >= 0.")
    return parsed


def _parse_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    return parsed
