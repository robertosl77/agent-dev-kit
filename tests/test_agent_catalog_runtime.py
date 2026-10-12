from agent_dev_kit.agent_catalog import (
    build_enabled_definitions,
    create_enabled_agents,
    is_agent_enabled,
)
from agent_dev_kit.project_config import (
    ContextualAgentConfig,
    ProjectAgentDevKitConfig,
)
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


class FakeProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.created = []

    def create_agent(self, definition, *, handoffs=()):
        self.created.append(
            (definition.name, tuple(item.name for item in handoffs))
        )
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native=definition,
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)
        self.created.append(
            (f"handoffs:{agent.name}", tuple(item.name for item in handoffs))
        )

    async def run(self, agent, message, *, session=None):
        raise NotImplementedError

    def run_sync(self, agent, message, *, session=None):
        raise NotImplementedError


def make_config(enabled, agents=None):
    return ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=tuple(enabled),
        agents=agents or {},
    )


def test_only_enabled_agents_are_built():
    config = make_config(("pmo", "testing"))

    definitions = build_enabled_definitions(config)

    assert set(definitions) == {"pmo", "testing"}
    assert is_agent_enabled(config, "pmo")
    assert not is_agent_enabled(config, "security")


def test_only_enabled_agents_are_instantiated_and_triage_sees_only_them():
    config = make_config(("pmo", "testing", "triage"))
    provider = FakeProvider()

    handles = create_enabled_agents(provider, config)

    assert set(handles) == {"pmo", "testing", "triage"}
    assert provider.created == [
        ("Agent PMO", ()),
        ("Agent Testing", ()),
        ("Agent Triage", ()),
        ("handoffs:Agent PMO", ("Agent Triage",)),
        ("handoffs:Agent Testing", ("Agent Triage",)),
        ("handoffs:Agent Triage", ("Agent PMO", "Agent Testing")),
    ]


def test_contextual_instructions_apply_only_to_enabled_agent():
    config = make_config(
        ("pmo",),
        agents={
            "pmo": ContextualAgentConfig(
                key="pmo",
                extra_instructions=("Regla local PMO.",),
            ),
            "security": ContextualAgentConfig(
                key="security",
                extra_instructions=("Regla local Security.",),
            ),
        },
    )

    definitions = build_enabled_definitions(config)

    assert "Regla local PMO." in definitions["pmo"].instructions
    assert "security" not in definitions


def test_unknown_enabled_agent_fails_explicitly():
    config = make_config(("backend", "super_agent"))

    try:
        build_enabled_definitions(config)
    except ValueError as exc:
        assert "super_agent" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_enabled_agent_receives_consuming_project_stack():
    config = ProjectAgentDevKitConfig(
        name="LibreriaIngles",
        stack={
            "backend": {"language": "Python", "framework": "FastAPI"},
            "database": {"engine": "SQLite"},
        },
        provider=ProviderConfig(provider="fake"),
        enabled_agents=("backend",),
        agents={},
    )

    definitions = build_enabled_definitions(config)
    instructions = definitions["backend"].instructions

    assert "LibreriaIngles" in instructions
    assert "Python" in instructions
    assert "FastAPI" in instructions
    assert "SQLite" in instructions


def test_global_user_preferences_are_injected_into_matching_agent():
    config = make_config(("backend",))

    definitions = build_enabled_definitions(config)

    instructions = definitions["backend"].instructions
    assert "modular_structure" in instructions
    assert "single_responsibility_owner" in instructions


def test_git_workflow_policy_is_injected_into_agent_context():
    config = ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=("pmo",),
        agents={},
    )

    definitions = build_enabled_definitions(config)
    instructions = definitions["pmo"].instructions

    assert "Git workflow policy enforced by Agent Dev Kit in code" in instructions
    assert "production: main" in instructions
    assert "integration: development" in instructions
    assert "explicit human authorization" in instructions
