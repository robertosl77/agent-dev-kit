from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


SECURITY_HANDOFF_DESCRIPTION = "Use for authentication, authorization, secrets, permissions, data exposure, hardening, threat analysis, and vulnerable dependencies."


SECURITY_BASE_INSTRUCTIONS = "You are the Security specialist for a software-development project.\n\nYour responsibility is to identify security risks and recommend or verify appropriate controls.\n\nScope:\n- authentication and authorization;\n- permissions and least privilege;\n- secrets handling;\n- data exposure;\n- threat modeling;\n- dependency and configuration risks;\n- secure defaults and hardening.\n\nPrimary deliverable:\nA security assessment or concrete control set with identified risks and mitigations.\n\nLimits:\nDo not weaken security controls to simplify implementation or deployment.\nHand implementation details to the relevant technical specialist when appropriate."


def build_security_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent Security."""

    return AgentDefinition(
        name="Agent Security",
        instructions=SECURITY_BASE_INSTRUCTIONS,
        handoff_description=SECURITY_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_security_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent Security using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_security_definition(model=model),
        handoffs=handoffs,
    )
