from agent_dev_kit.agents.agent_observability import build_observability_definition, create_observability_agent
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def create_agent(self, definition, *, handoffs=()):
        return AgentHandle(provider=self.key, name=definition.name, native=definition)

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def test_observability_contract():
    definition = build_observability_definition()
    text = definition.instructions.lower()
    assert definition.name == "Agent Observability"
    assert "logging" in text
    assert "metrics" in text
    assert "traces" in text
    assert "alerts" in text


def test_observability_is_provider_neutral():
    handle = create_observability_agent(FakeProvider())
    assert handle.provider == "fake"
    assert handle.name == "Agent Observability"
