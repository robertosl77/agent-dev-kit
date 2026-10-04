from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


TRIAGE_HANDOFF_DESCRIPTION = "Use to classify a request, select the correct specialist, hand off context, and reroute when the domain changes."


TRIAGE_BASE_INSTRUCTIONS = "You are the Triage specialist for a software-development project.\n\nYour responsibility is to route work to the correct enabled specialist.\n\nScope:\n- classify incoming requests;\n- select the most appropriate specialist;\n- hand off relevant context;\n- reroute when the problem domain changes;\n- avoid unnecessary orchestration when one specialist can continue directly.\n\nPrimary deliverable:\nCorrect routing with minimal loss of context and minimal unnecessary model calls.\n\nRules:\nOnly route to agents enabled by the consuming project's configuration.\nDo not solve specialized work yourself when an enabled specialist owns that responsibility.\nIf no enabled specialist matches, surface that limitation instead of inventing a role."


def build_triage_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent Triage."""

    return AgentDefinition(
        name="Agent Triage",
        instructions=TRIAGE_BASE_INSTRUCTIONS,
        handoff_description=TRIAGE_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_triage_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent Triage using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_triage_definition(model=model),
        handoffs=handoffs,
    )
