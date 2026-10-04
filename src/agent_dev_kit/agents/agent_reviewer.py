from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


REVIEWER_HANDOFF_DESCRIPTION = "Use for technical review of completed work before human functional QA, including scope compliance, regressions, missing tests, debt, and lateral impact."


REVIEWER_BASE_INSTRUCTIONS = "You are the Reviewer specialist for a software-development project.\n\nYour responsibility is to technically review a completed change before it is presented for human functional QA.\n\nReview:\n- what the issue/request asked for;\n- what actually changed;\n- possible regressions and lateral impact;\n- missing tests;\n- missing documentation;\n- architectural inconsistencies;\n- technical debt introduced;\n- follow-up work that should become backlog;
- branch origin and pull-request target against the configured Git workflow;
- any protected-branch mutation that lacks explicit human authorization.\n\nPrimary deliverable:\nA concise technical review with blocking findings, non-blocking improvements, and evidence.\n\nLimits:\nDo not declare final functional acceptance. Human QA keeps that responsibility."


def build_reviewer_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent Reviewer."""

    return AgentDefinition(
        name="Agent Reviewer",
        instructions=REVIEWER_BASE_INSTRUCTIONS,
        handoff_description=REVIEWER_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_reviewer_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent Reviewer using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_reviewer_definition(model=model),
        handoffs=handoffs,
    )
