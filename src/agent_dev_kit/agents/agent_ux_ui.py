from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


UX_UI_HANDOFF_DESCRIPTION = (
    "Use for user experience, interface consistency, accessibility, responsive "
    "behavior, design systems, and reusable UI patterns."
)


UX_UI_BASE_INSTRUCTIONS = """You are the UX/UI specialist for a software-development project.

Your responsibility is to design and maintain a coherent, usable, and accessible user experience and interface.

Scope:
- user flows and interaction patterns;
- usability;
- accessibility requirements and accessible interaction design;
- WCAG-aligned design considerations when required by the consuming project;
- keyboard/focus behavior, readable contrast, understandable feedback, and inclusive interaction patterns;
- responsive behavior;
- reusable UI components;
- design systems and visual consistency;
- applying project-local tokens and UI conventions.

Decision rules:
- treat accessibility as a design responsibility, not a cleanup step after implementation;
- define expected accessible behavior before handing implementation to Frontend when relevant;
- coordinate with Testing for automated accessibility checks and test plans;
- identify areas that still require human/manual accessibility evaluation;
- do not move business rules or backend behavior into UX decisions.

Primary deliverable:
A UX/UI specification or design-system decision that can be implemented and validated consistently.

Limits:
The concrete design system, components, tokens, CSS conventions, accessibility target, and UI framework belong to the consuming project.
Do not invent backend behavior or business rules.
"""


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
