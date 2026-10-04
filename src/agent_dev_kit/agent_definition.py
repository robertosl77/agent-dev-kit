from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Provider-neutral definition of an Agent Dev Kit specialist."""

    name: str
    instructions: str
    handoff_description: str | None = None
    model: str | None = None
