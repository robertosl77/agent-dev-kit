from agent_dev_kit import ProviderConfig, ProviderRegistry
from agent_dev_kit.providers.provider_base import AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def create_agent(self, definition, *, handoffs=()):
        raise NotImplementedError

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def test_registry_creates_registered_provider():
    registry = ProviderRegistry()
    registry.register("fake", lambda config: FakeProvider())

    provider = registry.create(ProviderConfig(provider="fake"))

    assert isinstance(provider, FakeProvider)
    assert provider.key == "fake"


def test_registry_is_case_insensitive():
    registry = ProviderRegistry()
    registry.register("fake", lambda config: FakeProvider())

    provider = registry.create(ProviderConfig(provider="FAKE"))

    assert provider.key == "fake"


def test_registry_rejects_unknown_provider():
    registry = ProviderRegistry()

    try:
        registry.create(ProviderConfig(provider="missing"))
    except ValueError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
