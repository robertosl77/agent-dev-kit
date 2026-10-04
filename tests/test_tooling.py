from agent_dev_kit.agent_catalog import create_enabled_agents
from agent_dev_kit.project_config import (
    ContextualAgentConfig,
    ProjectAgentDevKitConfig,
)
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider
from agent_dev_kit.tooling import ToolRegistry


class ToolAwareProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.received_tools = {}

    def create_agent(self, definition, *, handoffs=(), tools=()):
        self.received_tools[definition.name] = tuple(tool.key for tool in tools)
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native=definition,
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def make_config(tools):
    return ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=("pmo",),
        agents={
            "pmo": ContextualAgentConfig(
                key="pmo",
                tools=tuple(tools),
            )
        },
    )


def test_registered_tool_is_passed_to_configured_agent():
    registry = ToolRegistry()
    registry.register(
        "github_issues",
        provider="fake",
        native=object(),
    )
    provider = ToolAwareProvider()

    create_enabled_agents(
        provider,
        make_config(("github_issues",)),
        tool_registry=registry,
    )

    assert provider.received_tools["Agent PMO"] == ("github_issues",)


def test_missing_tool_registry_fails_explicitly():
    provider = ToolAwareProvider()

    try:
        create_enabled_agents(
            provider,
            make_config(("github_issues",)),
        )
    except ValueError as exc:
        assert "ToolRegistry" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_unregistered_tool_fails_explicitly():
    provider = ToolAwareProvider()
    registry = ToolRegistry()

    try:
        create_enabled_agents(
            provider,
            make_config(("github_issues",)),
            tool_registry=registry,
        )
    except ValueError as exc:
        assert "github_issues" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
