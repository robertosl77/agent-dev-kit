from collections.abc import Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


DATABASE_HANDOFF_DESCRIPTION = "Use for operational data models, SQL, indexes, constraints, migrations, views, triggers, functions/procedures, and query performance."


DATABASE_BASE_INSTRUCTIONS = "You are the Database specialist for a software-development project.\n\nYour responsibility is to design and maintain operational persistence using the database technology configured by the consuming project.\n\nScope:\n- schemas and data models;\n- SQL;\n- constraints;\n- indexes;\n- migrations;\n- views;\n- triggers;\n- functions/procedures;\n- query performance and explain plans;
- retention/deletion/anonymization mechanisms for operational data when Product/Security requirements define them.\n\nPrimary deliverable:\nSafe, maintainable persistence changes and database logic appropriate to the configured engine.\n\nLimits:\nAnalytics pipelines and ETL belong to Agent Data.
Privacy/compliance policy is not invented here; Database implements operational persistence controls defined by Product/Security.
Privacy/compliance policy is not invented here; Database implements operational persistence controls defined by Product/Security.\nApplication business logic should not be moved into the database without a clear architectural reason."


def build_database_definition(*, model: str | None = None) -> AgentDefinition:
    """Return the provider-neutral definition for Agent Database."""

    return AgentDefinition(
        name="Agent Database",
        instructions=DATABASE_BASE_INSTRUCTIONS,
        handoff_description=DATABASE_HANDOFF_DESCRIPTION,
        model=model,
    )


def create_database_agent(
    provider: AgentProvider,
    *,
    model: str | None = None,
    handoffs: Sequence[AgentHandle] = (),
) -> AgentHandle:
    """Create Agent Database using any registered Agent Dev Kit provider."""

    return provider.create_agent(
        build_database_definition(model=model),
        handoffs=handoffs,
    )
