from agent_dev_kit import AgentDefinition
from agent_dev_kit.agents.agent_testing import (
    build_testing_definition,
    create_testing_agent,
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


def test_testing_definition_has_expected_contract():
    definition = build_testing_definition()

    assert isinstance(definition, AgentDefinition)
    assert definition.name == "Agent Testing"
    assert "unit tests" in definition.instructions.lower()
    assert "regression" in definition.instructions.lower()
    assert "white-box" in definition.instructions.lower()
    assert "human qa" in definition.instructions.lower()
    assert "deterministic" in definition.instructions.lower()
    assert definition.handoff_description


def test_testing_definition_accepts_model_override():
    definition = build_testing_definition(model="example-model")

    assert definition.model == "example-model"


def test_testing_can_be_created_with_any_provider():
    provider = FakeProvider()

    handle = create_testing_agent(provider)

    assert handle.provider == "fake"
    assert handle.name == "Agent Testing"
    assert provider.definition.name == "Agent Testing"
    assert provider.handoffs == ()
