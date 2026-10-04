from agent_dev_kit import AgentDefinition
from agent_dev_kit.agents.agent_security import build_security_definition


def test_security_definition_covers_defensive_security_testing():
    definition = build_security_definition()

    assert isinstance(definition, AgentDefinition)
    assert definition.name == "Agent Security"

    instructions = definition.instructions.lower()

    assert "sql/command/template injection" in instructions
    assert "cross-site scripting" in instructions
    assert "broken object-level authorization" in instructions
    assert "path traversal" in instructions
    assert "security regression" in instructions
    assert "testing" in instructions
    assert "ci/cd" in instructions
    assert "destructive testing" in instructions
