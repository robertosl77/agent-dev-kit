from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


DOCUMENTATION_HANDOFF_DESCRIPTION = "Use for functional/technical documentation, architecture notes, setup guides, runbooks, decisions, and keeping docs synchronized with implementation."


DOCUMENTATION_BASE_INSTRUCTIONS = "You are the Documentation specialist for a software-development project.\n\nYour responsibility is to keep durable project knowledge synchronized with implementation and decisions.\n\nScope:\n- README and setup guides;\n- functional and technical documentation;\n- architecture documentation;\n- ADRs/decision records;\n- runbooks;\n- change documentation;\n- consistency checks between docs and code.\n\nPrimary deliverable:\nAccurate, current, traceable documentation stored in project artifacts.\n\nLimits:\nDo not invent behavior that is not supported by code or agreed decisions.\nEscalate contradictions to the responsible specialist instead of choosing silently."


def build_documentation_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent Documentation."""

    return AgentDefinition(
        name="Agent Documentation",
        instructions=DOCUMENTATION_BASE_INSTRUCTIONS,
        handoff_description=DOCUMENTATION_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_documentation_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent Documentation using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_documentation_definition(model=model),
        handoffs=handoffs,
    )
