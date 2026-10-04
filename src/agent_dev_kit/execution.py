from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from agent_dev_kit.preferences import PreferenceProfile
from agent_dev_kit.provider_config import ProviderConfig, ProviderTargetConfig
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
    config: ProviderConfig
    tool_registry: ToolRegistry | None = None
    preference_profile: PreferenceProfile | None = None
    _target_index: int = 0
    _kit: DevAgentKit | None = None

    @property
    def current_target(self) -> ProviderTargetConfig:
        return self.config.targets()[self._target_index]

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
                next_target = self._next_target()
                if next_target is None or self.config.fallback_policy == "never":
                    raise

                if confirm_switch is None:
                    raise ProviderFallbackRequired(
                        current_provider=self.current_target.provider,
                        next_provider=next_target.provider,
                        cause=exc,
                    ) from exc

                if not confirm_switch(
                    self.current_target,
                    next_target,
                    exc,
                ):
                    raise

                self._target_index += 1
                self._kit = None

    def reset_primary(self) -> None:
        self._target_index = 0
        self._kit = None

    def _next_target(self) -> ProviderTargetConfig | None:
        targets = self.config.targets()
        next_index = self._target_index + 1
        if next_index >= len(targets):
            return None
        return targets[next_index]

    def _build_current(self) -> DevAgentKit:
        target = self.current_target
        provider = self.registry.create(target.as_provider_config())
        config = self._config_for_target(target)
        return DevAgentKit.build(
            config,
            provider,
            tool_registry=self.tool_registry,
            preference_profile=self.preference_profile,
        )

    def _config_for_target(
        self,
        target: ProviderTargetConfig,
    ):
        from dataclasses import replace

        return replace(
            self._project_config,
            provider=target.as_provider_config(),
        )

    @classmethod
    def for_project(
        cls,
        *,
        registry: ProviderRegistry,
        project_config,
        tool_registry: ToolRegistry | None = None,
        preference_profile: PreferenceProfile | None = None,
    ) -> "ProviderRuntime":
        runtime = cls(
            registry=registry,
            config=project_config.provider,
            tool_registry=tool_registry,
            preference_profile=preference_profile,
        )
        runtime._project_config = project_config
        return runtime
