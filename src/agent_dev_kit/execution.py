from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TypeVar

from agent_dev_kit.preferences import PreferenceProfile
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderTargetConfig
from agent_dev_kit.provider_errors import (
    ProviderFallbackRequired,
    ProviderRecoverableError,
)
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.runtime import DevAgentKit
from agent_dev_kit.tooling import ToolRegistry


T = TypeVar("T")
FallbackConfirmation = Callable[
    [ProviderTargetConfig, ProviderTargetConfig, ProviderRecoverableError],
    bool,
]


@dataclass(slots=True)
class ProviderRuntime:
    """Build Agent Dev Kit against primary/fallback providers on demand."""

    registry: ProviderRegistry
    project_config: ProjectAgentDevKitConfig
    tool_registry: ToolRegistry | None = None
    preference_profile: PreferenceProfile | None = None
    _target_index: int = 0
    _kit: DevAgentKit | None = field(default=None, init=False)

    @property
    def current_target(self) -> ProviderTargetConfig:
        return self.project_config.provider.targets()[self._target_index]

    @property
    def kit(self) -> DevAgentKit:
        if self._kit is None:
            self._kit = self._build_current()
        return self._kit

    def run_with_fallback_sync(
        self,
        operation: Callable[[DevAgentKit], T],
        *,
        confirm_switch: FallbackConfirmation | None = None,
    ) -> T:
        while True:
            try:
                return operation(self.kit)
            except ProviderRecoverableError as exc:
                self.switch_after_error(
                    exc,
                    confirm_switch=confirm_switch,
                )

    def switch_after_error(
        self,
        error: ProviderRecoverableError,
        *,
        confirm_switch: FallbackConfirmation | None = None,
    ) -> DevAgentKit:
        """Move to the next provider only after policy/approval checks."""

        next_target = self._next_target()
        config = self.project_config.provider

        if next_target is None or config.fallback_policy == "never":
            raise error

        if confirm_switch is None:
            raise ProviderFallbackRequired(
                current_provider=self.current_target.provider,
                next_provider=next_target.provider,
                cause=error,
            ) from error

        if not confirm_switch(
            self.current_target,
            next_target,
            error,
        ):
            raise error

        self._target_index += 1
        self._kit = None
        return self.kit

    def reset_primary(self) -> None:
        self._target_index = 0
        self._kit = None

    def _next_target(self) -> ProviderTargetConfig | None:
        targets = self.project_config.provider.targets()
        next_index = self._target_index + 1
        if next_index >= len(targets):
            return None
        return targets[next_index]

    def _build_current(self) -> DevAgentKit:
        target = self.current_target
        provider_config = target.as_provider_config()
        provider = self.registry.create(provider_config)
        config = replace(
            self.project_config,
            provider=provider_config,
        )
        return DevAgentKit.build(
            config,
            provider,
            tool_registry=self.tool_registry,
            preference_profile=self.preference_profile,
        )
