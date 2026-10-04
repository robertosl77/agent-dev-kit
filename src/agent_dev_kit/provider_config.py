from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Configuration supplied by the project consuming Agent Dev Kit."""

    provider: str = "openai"
    default_model: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
