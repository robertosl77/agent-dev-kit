from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def create_agent(self, definition, *, handoffs=()):
        raise NotImplementedError

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def test_provider_rejects_foreign_agent_handle():
    provider = FakeProvider()
    handle = AgentHandle(provider="other", name="Other", native=object())

    try:
        provider._validate_handle(handle)
    except ValueError as exc:
        assert "other" in str(exc)
        assert "fake" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
