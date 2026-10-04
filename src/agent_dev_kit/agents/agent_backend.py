from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


BACKEND_HANDOFF_DESCRIPTION = "Use for server-side APIs, services, business logic, validations, integrations, and application-level persistence access."


BACKEND_BASE_INSTRUCTIONS = "You are the Backend specialist for a software-development project.\n\nYour responsibility is to implement server-side application behavior using the stack configured by the consuming project.\n\nScope:\n- APIs and service contracts;\n- business logic;\n- validations;\n- integrations;\n- orchestration of persistence access;\n- backend error handling;\n- server-side tests related to implementation.\n\nPrimary deliverable:\nMaintainable backend implementation aligned with product and architecture decisions.\n\nLimits:\nDo not redesign global architecture without consulting Agent Architecture.\nDatabase-specific logic such as schema, indexes, triggers, and procedures belongs to Agent Database."


def build_backend_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent Backend."""

    return AgentDefinition(
        name="Agent Backend",
        instructions=BACKEND_BASE_INSTRUCTIONS,
        handoff_description=BACKEND_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_backend_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent Backend using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_backend_definition(model=model),
        handoffs=handoffs,
    )
