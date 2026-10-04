from agent_dev_kit.agents.agent_performance import build_performance_definition, create_performance_agent
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def create_agent(self, definition, *, handoffs=()):
        return AgentHandle(provider=self.key, name=definition.name, native=definition)

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def test_performance_contract():
    definition = build_performance_definition()
    text = definition.instructions.lower()
    assert definition.name == "Agent Performance"
    assert "measure" in text
    assert "token" in text
    assert "deterministic" in text


def test_performance_is_provider_neutral():
    handle = create_performance_agent(FakeProvider())
    assert handle.provider == "fake"
    assert handle.name == "Agent Performance"
