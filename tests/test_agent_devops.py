from agent_dev_kit.agents.agent_devops import build_devops_definition, create_devops_agent
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def create_agent(self, definition, *, handoffs=()):
        return AgentHandle(provider=self.key, name=definition.name, native=definition)

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def test_devops_contract():
    definition = build_devops_definition()
    assert definition.name == "Agent DevOps"
    assert "docker" in definition.instructions.lower()
    assert "ci/cd" in definition.instructions.lower()
    assert "secret" in definition.instructions.lower()
    assert "sast" in definition.instructions.lower()
    assert "dependency/sca" in definition.instructions.lower()


def test_devops_is_provider_neutral():
    handle = create_devops_agent(FakeProvider())
    assert handle.provider == "fake"
    assert handle.name == "Agent DevOps"
