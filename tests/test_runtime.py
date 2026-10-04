from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)
from agent_dev_kit.runtime import DevAgentKit


class FakeProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.handoffs = {}
        self.next_agent_name = None

    def create_agent(self, definition, *, handoffs=()):
        handle = AgentHandle(
            provider=self.key,
            name=definition.name,
            native={"name": definition.name},
        )
        self.handoffs[definition.name] = tuple(item.name for item in handoffs)
        return handle

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)
        self.handoffs[agent.name] = tuple(item.name for item in handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        name = self.next_agent_name or agent.name
        active = next(
            handle
            for handle in self._handles
            if handle.name == name
        )
        return ProviderRunResult(output=message, active_agent=active)

    def bind_handles(self, handles):
        self._handles = tuple(handles.values())


def config():
    return ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=("pmo", "testing", "triage"),
        agents={},
    )


def test_specialists_return_to_triage_and_triage_routes_to_specialists():
    provider = FakeProvider()
    kit = DevAgentKit.build(config(), provider)
    provider.bind_handles(kit.agents)

    assert provider.handoffs["Agent Triage"] == (
        "Agent PMO",
        "Agent Testing",
    )
    assert provider.handoffs["Agent PMO"] == ("Agent Triage",)
    assert provider.handoffs["Agent Testing"] == ("Agent Triage",)


def test_conversation_persists_last_active_specialist():
    provider = FakeProvider()
    kit = DevAgentKit.build(config(), provider)
    provider.bind_handles(kit.agents)
    conversation = kit.conversation()

    assert conversation.active_agent.name == "Agent Triage"

    provider.next_agent_name = "Agent PMO"
    conversation.ask_sync("route")
    assert conversation.active_agent.name == "Agent PMO"

    provider.next_agent_name = None
    conversation.ask_sync("continue")
    assert conversation.active_agent.name == "Agent PMO"


def test_reset_route_returns_to_triage():
    provider = FakeProvider()
    kit = DevAgentKit.build(config(), provider)
    provider.bind_handles(kit.agents)
    conversation = kit.conversation(start_agent="testing")

    conversation.reset_route()

    assert conversation.active_agent.name == "Agent Triage"
