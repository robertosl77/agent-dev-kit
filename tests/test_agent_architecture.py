from agent_dev_kit.agents.agent_architecture import (
    build_architecture_definition,
    create_architecture_agent,
)
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def create_agent(self, definition, *, handoffs=()):
        return AgentHandle(provider=self.key, name=definition.name, native=definition)

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def test_architecture_contract():
    definition = build_architecture_definition()
    text = definition.instructions.lower()
    assert definition.name == "Agent Architecture"
    assert "boundaries" in text
    assert "duplicated" in text
    assert "current task" in text
    assert "benefit" in text


def test_architecture_is_provider_neutral():
    handle = create_architecture_agent(FakeProvider())
    assert handle.provider == "fake"
    assert handle.name == "Agent Architecture"
