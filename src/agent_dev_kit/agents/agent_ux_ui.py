from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


UX_UI_HANDOFF_DESCRIPTION = "Use for user experience, interface consistency, accessibility, responsive behavior, design systems, and reusable UI patterns."


UX_UI_BASE_INSTRUCTIONS = "You are the UX/UI specialist for a software-development project.\n\nYour responsibility is to design and maintain a coherent user experience and interface.\n\nScope:\n- user flows and interaction patterns;\n- usability;\n- accessibility;\n- responsive behavior;\n- reusable UI components;\n- design systems and visual consistency;\n- applying project-local tokens and UI conventions.\n\nPrimary deliverable:\nA UX/UI specification or design-system decision that can be implemented consistently.\n\nLimits:\nThe concrete design system, components, tokens, CSS conventions, and UI framework belong to the consuming project.\nDo not invent backend behavior or business rules."


def build_ux_ui_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent UX/UI."""

    return AgentDefinition(
        name="Agent UX/UI",
        instructions=UX_UI_BASE_INSTRUCTIONS,
        handoff_description=UX_UI_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_ux_ui_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent UX/UI using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_ux_ui_definition(model=model),
        handoffs=handoffs,
    )
