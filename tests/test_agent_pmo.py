from agent_dev_kit import AgentDefinition
from agent_dev_kit.agents.agent_pmo import (
    build_pmo_definition,
    create_pmo_agent,
)
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.definition = None
        self.handoffs = None

    def create_agent(self, definition, *, handoffs=()):
        self.definition = definition
        self.handoffs = tuple(handoffs)
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native={"definition": definition},
        )

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def test_pmo_definition_has_expected_contract():
    definition = build_pmo_definition()

    assert isinstance(definition, AgentDefinition)
    assert definition.name == "Agent PMO"
    assert "backlog" in definition.instructions.lower()
    assert "blocked" in definition.instructions.lower()
    assert "human" in definition.instructions.lower()
    assert definition.handoff_description


def test_pmo_definition_accepts_model_override():
    definition = build_pmo_definition(model="example-model")

    assert definition.model == "example-model"


def test_pmo_can_be_created_with_any_provider():
    provider = FakeProvider()

    handle = create_pmo_agent(provider)

    assert handle.provider == "fake"
    assert handle.name == "Agent PMO"
    assert provider.definition.name == "Agent PMO"
    assert provider.handoffs == ()
