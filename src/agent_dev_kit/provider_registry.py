import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import AgentProvider


ProviderFactory = Callable[[ProviderConfig], AgentProvider]
CredentialSource = Callable[[str], "str | None"]


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """What a person needs to know to use a built-in provider."""

    key: str
    label: str
    env_vars: tuple[str, ...]
    extra: str
    key_url: str
    import_name: str
    # Documented key prefixes, used to warn about a badly pasted key.
    key_prefixes: tuple[str, ...] = ()

    @property
    def env_var(self) -> str:
        return self.env_vars[0]

    def key_from_env(self) -> str | None:
        for name in self.env_vars:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return None

    def env_var_in_use(self) -> str | None:
        for name in self.env_vars:
            if os.environ.get(name, "").strip():
                return name
        return None

    def is_installed(self) -> bool:
        from importlib.util import find_spec

        try:
            return find_spec(self.import_name) is not None
        except (ImportError, ValueError):
            return False


BUILTIN_PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        key="anthropic",
        label="Anthropic (Claude)",
        env_vars=("ANTHROPIC_API_KEY",),
        extra="anthropic",
        key_url="https://platform.claude.com/settings/keys",
        import_name="anthropic",
        key_prefixes=("sk-ant-",),
    ),
    "gemini": ProviderSpec(
        key="gemini",
        label="Google Gemini",
        env_vars=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        extra="gemini",
        key_url="https://aistudio.google.com/apikey",
        import_name="google.genai",
    ),
    "openai": ProviderSpec(
        key="openai",
        label="OpenAI",
        env_vars=("OPENAI_API_KEY",),
        extra="openai",
        key_url="https://platform.openai.com/api-keys",
        import_name="agents",
        key_prefixes=("sk-",),
    ),
}


class ProviderRegistry:
    """Registry that lets consumers add providers without changing agent roles."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, key: str, factory: ProviderFactory) -> None:
        normalized = key.strip().lower()
        if not normalized:
            raise ValueError("Provider key cannot be empty.")
        self._factories[normalized] = factory

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

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


def build_default_registry(
    credentials: CredentialSource | Mapping[str, str] | None = None,
) -> ProviderRegistry:
    """Registry with the built-in providers.

    ``credentials`` supplies API keys at runtime (for example, typed in the CLI
    menu) without environment variables. When it returns nothing for a
    provider, that provider's SDK falls back to its usual environment
    variable. Keys are only kept in memory.
    """

    if credentials is None:
        resolve: CredentialSource = lambda key: None  # noqa: E731
    elif isinstance(credentials, Mapping):
        mapping = dict(credentials)
        resolve = lambda key: mapping.get(key)  # noqa: E731
    else:
        resolve = credentials

    registry = ProviderRegistry()

    def openai_factory(config: ProviderConfig) -> AgentProvider:
        # Import lazily so the core package stays provider-neutral.
        from agent_dev_kit.providers.provider_openai import OpenAIProvider

        return OpenAIProvider(
            api_key=resolve("openai"),
            default_model=config.default_model,
            options=config.options,
        )

    def anthropic_factory(config: ProviderConfig) -> AgentProvider:
        from agent_dev_kit.providers.provider_anthropic import AnthropicProvider

        return AnthropicProvider(
            api_key=resolve("anthropic"),
            default_model=config.default_model,
            options=config.options,
        )

    def gemini_factory(config: ProviderConfig) -> AgentProvider:
        from agent_dev_kit.providers.provider_gemini import GeminiProvider

        return GeminiProvider(
            api_key=resolve("gemini"),
            default_model=config.default_model,
            options=config.options,
        )

    registry.register("openai", openai_factory)
    registry.register("anthropic", anthropic_factory)
    registry.register("gemini", gemini_factory)
    return registry
