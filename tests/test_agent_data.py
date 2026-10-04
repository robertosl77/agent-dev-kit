from agent_dev_kit.agents.agent_data import build_data_definition, create_data_agent
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def create_agent(self, definition, *, handoffs=()):
        return AgentHandle(provider=self.key, name=definition.name, native=definition)

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def test_data_contract():
    definition = build_data_definition()
    text = definition.instructions.lower()
    assert definition.name == "Agent Data"
    assert "etl" in text
    assert "data quality" in text
    assert "agent database" in text


def test_data_is_provider_neutral():
    handle = create_data_agent(FakeProvider())
    assert handle.provider == "fake"
    assert handle.name == "Agent Data"
