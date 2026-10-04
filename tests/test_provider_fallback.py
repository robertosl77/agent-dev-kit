import pytest

from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import (
    ProviderConfig,
    ProviderTargetConfig,
)
from agent_dev_kit.provider_errors import (
    ProviderFallbackRequired,
    ProviderQuotaExceeded,
)
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)


class FakeProvider(AgentProvider):
    def __init__(self, key, *, fail=False):
        self.key = key
        self.fail = fail

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native=definition,
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        if self.fail:
            raise ProviderQuotaExceeded(
                f"{self.key} exhausted",
                provider=self.key,
            )
        return ProviderRunResult(
            output=f"{self.key}:{message}",
            active_agent=agent,
        )


def make_runtime(*, policy="ask"):
    registry = ProviderRegistry()
    registry.register(
        "primary",
        lambda config: FakeProvider("primary", fail=True),
    )
    registry.register(
        "backup",
        lambda config: FakeProvider("backup"),
    )

    config = ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(
            provider="primary",
            fallbacks=(
                ProviderTargetConfig(provider="backup"),
            ),
            fallback_policy=policy,
        ),
        enabled_agents=("backend",),
        agents={},
    )
    return ProviderRuntime(
        registry=registry,
        project_config=config,
    )


def operation(kit):
    return kit.conversation(
        start_agent="backend"
    ).ask_sync("hello").output


def test_fallback_requires_explicit_approval_when_callback_missing():
    runtime = make_runtime()

    with pytest.raises(ProviderFallbackRequired):
        runtime.run_with_fallback_sync(operation)


def test_approved_fallback_rebuilds_agents_with_next_provider():
    runtime = make_runtime()

    output = runtime.run_with_fallback_sync(
        operation,
        confirm_switch=lambda current, next_target, error: True,
    )

    assert output == "backup:hello"
    assert runtime.current_target.provider == "backup"


def test_rejected_fallback_surfaces_original_error():
    runtime = make_runtime()

    with pytest.raises(ProviderQuotaExceeded):
        runtime.run_with_fallback_sync(
            operation,
            confirm_switch=lambda current, next_target, error: False,
        )


def test_never_policy_does_not_offer_fallback():
    runtime = make_runtime(policy="never")

    with pytest.raises(ProviderQuotaExceeded):
        runtime.run_with_fallback_sync(
            operation,
            confirm_switch=lambda current, next_target, error: True,
        )
