from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class GatewayLifecycleConfig:
    """In-memory Gateway session lifecycle limits."""

    session_ttl_seconds: int = 3600
    max_sessions: int = 100


def gateway_lifecycle_from_mapping(
    data: Mapping[str, Any] | None,
) -> GatewayLifecycleConfig:
    if data is None:
        return GatewayLifecycleConfig()
    if not isinstance(data, Mapping):
        raise ValueError("'gateway' must be a mapping.")

    allowed = {"session_ttl_seconds", "max_sessions"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            "Unknown gateway field(s): "
            + ", ".join(sorted(str(value) for value in unknown))
        )

    return GatewayLifecycleConfig(
        session_ttl_seconds=_positive_int(
            data.get("session_ttl_seconds", 3600),
            "gateway.session_ttl_seconds",
        ),
        max_sessions=_positive_int(
            data.get("max_sessions", 100),
            "gateway.max_sessions",
        ),
    )


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer > 0.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer > 0.") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be > 0.")
    return parsed
