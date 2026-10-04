from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderTargetConfig:
    provider: str
    default_model: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def as_provider_config(self) -> "ProviderConfig":
        return ProviderConfig(
            provider=self.provider,
            default_model=self.default_model,
            options=dict(self.options),
        )


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Configuration supplied by the project consuming Agent Dev Kit."""

    provider: str = "openai"
    default_model: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    fallbacks: tuple[ProviderTargetConfig, ...] = ()
    fallback_policy: str = "never"

    def __post_init__(self) -> None:
        policy = self.fallback_policy.strip().lower()
        if policy not in {"never", "ask"}:
            raise ValueError(
                "fallback_policy must be either 'never' or 'ask'."
            )
        object.__setattr__(self, "fallback_policy", policy)

    def targets(self) -> tuple[ProviderTargetConfig, ...]:
        primary = ProviderTargetConfig(
            provider=self.provider,
            default_model=self.default_model,
            options=dict(self.options),
        )
        return (primary,) + self.fallbacks
