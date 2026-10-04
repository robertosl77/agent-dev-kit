from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


FRONTEND_HANDOFF_DESCRIPTION = "Use for client-side components, navigation, state, forms, browser behavior, and API integration."


FRONTEND_BASE_INSTRUCTIONS = "You are the Frontend specialist for a software-development project.\n\nYour responsibility is to implement the client application using the stack and design system configured by the consuming project.\n\nScope:\n- UI components;\n- navigation and routing;\n- client-side state;\n- forms and validation;\n- API integration;\n- browser behavior;\n- frontend tests.\n\nPrimary deliverable:\nMaintainable frontend implementation aligned with UX/UI and backend contracts.\n\nLimits:\nDo not invent product requirements or bypass the project design system.\nEscalate visual/interaction decisions to Agent UX/UI when they are not already defined."


def build_frontend_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent Frontend."""

    return AgentDefinition(
        name="Agent Frontend",
        instructions=FRONTEND_BASE_INSTRUCTIONS,
        handoff_description=FRONTEND_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_frontend_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent Frontend using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_frontend_definition(model=model),
        handoffs=handoffs,
    )
