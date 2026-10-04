from dataclasses import dataclass
from typing import Any, Callable, Iterable

from agent_dev_kit.git_mutation import GitMutationGateway


@dataclass(slots=True)
class ToolHandle:
    """Provider-specific native tool exposed through a neutral key."""

    provider: str
    key: str
    native: Any
    effect: str = "opaque"
    enforced_policy: str | None = None


class ToolRegistry:
    """Tools supplied by the consuming application at runtime.

    Generic tools are opaque trusted extensions. Supported Git write tools must
    be registered with register_git_mutation(), which constructs the provider
    native tool around a GitMutationGateway.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolHandle] = {}

    def register(
        self,
        key: str,
        *,
        provider: str,
        native: Any,
    ) -> ToolHandle:
        normalized = self.normalize_key(key)
        if not normalized:
            raise ValueError("Tool key cannot be empty.")

        handle = ToolHandle(
            provider=provider.strip().lower(),
            key=normalized,
            native=native,
        )
        self._tools[normalized] = handle
        return handle

    def register_git_mutation(
        self,
        key: str,
        *,
        provider: str,
        gateway: GitMutationGateway,
        build_native: Callable[[GitMutationGateway], Any],
    ) -> ToolHandle:
        """Register a Git write tool whose implementation receives only the
        policy-enforced mutation gateway.

        This is the supported registration path for Git mutations. The native
        provider adapter is built here so integrations do not need a raw Git
        write callback exposed to the agent.
        """

        normalized = self.normalize_key(key)
        if not normalized:
            raise ValueError("Tool key cannot be empty.")
        if not isinstance(gateway, GitMutationGateway):
            raise TypeError(
                "Git mutation tools require a GitMutationGateway."
            )

        native = build_native(gateway)
        handle = ToolHandle(
            provider=provider.strip().lower(),
            key=normalized,
            native=native,
            effect="git_mutation",
            enforced_policy="git_policy_guard",
        )
        self._tools[normalized] = handle
        return handle

    def resolve(
        self,
        keys: Iterable[str],
        *,
        provider: str,
    ) -> tuple[ToolHandle, ...]:
        expected_provider = provider.strip().lower()
        resolved: list[ToolHandle] = []

        for raw_key in keys:
            key = self.normalize_key(raw_key)
            try:
                handle = self._tools[key]
            except KeyError as exc:
                raise ValueError(
                    f"Tool '{key}' is required but not registered."
                ) from exc

            if handle.provider != expected_provider:
                raise ValueError(
                    f"Tool '{key}' belongs to provider '{handle.provider}', "
                    f"not '{expected_provider}'."
                )

            resolved.append(handle)

        return tuple(resolved)

    @staticmethod
    def normalize_key(value: str) -> str:
        return value.strip().lower().replace("-", "_").replace(" ", "_")
