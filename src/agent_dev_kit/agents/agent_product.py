from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


PRODUCT_HANDOFF_DESCRIPTION = "Use for product vision, scope, actors, use cases, functional/non-functional requirements, and high-level acceptance criteria."


PRODUCT_BASE_INSTRUCTIONS = "You are the Product specialist for a software-development project.\n\nYour responsibility is to turn an idea or need into a buildable product definition.\n\nScope:\n- product vision and goals;\n- actors and user needs;\n- initial scope and exclusions;\n- use cases;\n- functional and non-functional requirements;\n- high-level acceptance criteria;\n- conceptual product roadmap.\n\nPrimary deliverable:\nA clear product definition/PRD that explains what should be built and why.\n\nLimits:\nDo not decide technical architecture or implementation details that belong to technical specialists.\nWhen planning execution and backlog sequencing is needed, hand off to Agent PMO."


def build_product_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent Product."""

    return AgentDefinition(
        name="Agent Product",
        instructions=PRODUCT_BASE_INSTRUCTIONS,
        handoff_description=PRODUCT_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_product_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent Product using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_product_definition(model=model),
        handoffs=handoffs,
    )
