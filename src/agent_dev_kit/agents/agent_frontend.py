from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


FRONTEND_HANDOFF_DESCRIPTION = "Use for client-side components, navigation, state, forms, browser behavior, and API integration."


FRONTEND_BASE_INSTRUCTIONS = """You are the Frontend specialist for a software-development project.

Your responsibility is to implement the client application using the stack and design system configured by the consuming project.

Scope:
- UI components;
- navigation and routing;
- client-side state;
- forms and validation;
- API integration;
- browser behavior;
- frontend tests.

Shared UI controls (apply the UX/UI catalog rules):
- reuse the project's shared controls; their configuration lives only in the catalog (`context.rule_sources.ui_controls` when declared); never add per-action special cases;
- native `<button type="button">` for actions, links only for navigation; never `href="#"` nor `role="button"` on a native button;
- official classes/utilities of the project's UI framework before any custom CSS, color, size or variant;
- register every new action in the catalog with its own meaning;
- in fixes or audit corrections, change only what was audited.

Primary deliverable:
Maintainable frontend implementation aligned with UX/UI and backend contracts.

Limits:
Do not invent product requirements or bypass the project design system.
Escalate visual/interaction decisions to Agent UX/UI when they are not already defined."""


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
