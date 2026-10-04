from collections.abc import Callable

from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import AgentProvider


ProviderFactory = Callable[[ProviderConfig], AgentProvider]


class ProviderRegistry:
    """Registry that lets consumers add providers without changing agent roles."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, key: str, factory: ProviderFactory) -> None:
        normalized = key.strip().lower()
        if not normalized:
            raise ValueError("Provider key cannot be empty.")
        self._factories[normalized] = factory

    def create(self, config: ProviderConfig) -> AgentProvider:
        key = config.provider.strip().lower()
        try:
            factory = self._factories[key]
        except KeyError as exc:
            available = ", ".join(sorted(self._factories)) or "none"
            raise ValueError(
                f"Unknown provider '{config.provider}'. "
                f"Registered providers: {available}."
            ) from exc
        return factory(config)


def build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()

    def openai_factory(config: ProviderConfig) -> AgentProvider:
        # Import lazily so the core package stays provider-neutral.
        from agent_dev_kit.providers.provider_openai import OpenAIProvider

        return OpenAIProvider()

    registry.register("openai", openai_factory)
    return registry
