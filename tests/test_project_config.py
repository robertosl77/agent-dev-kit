from pathlib import Path

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.project_config import (
    apply_contextual_config,
    load_project_config,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_project_and_contextual_agent_config(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: LibreriaIngles

stack:
  backend:
    language: Python
    framework: FastAPI
  frontend:
    framework: Angular
  ui:
    framework: Bootstrap
  database:
    engine: SQLite

provider:
  name: openai
  default_model: example-model

agents:
  enabled:
    - pmo
    - architecture
""",
    )
    write(
        tmp_path / ".agent-dev-kit" / "agents" / "pmo.yaml",
        """
agent: pmo

extra_instructions:
  - "Usar M-xxx para modernizaciones."
  - "QA funcional final es humano."

project_rules:
  final_qa: human
""",
    )

    config = load_project_config(tmp_path)

    assert config.name == "LibreriaIngles"
    assert config.stack["database"]["engine"] == "SQLite"
    assert config.provider.provider == "openai"
    assert config.provider.default_model == "example-model"
    assert config.enabled_agents == ("pmo", "architecture")
    assert config.agent("pmo").project_rules["final_qa"] == "human"


def test_apply_context_keeps_native_and_adds_local_rules():
    definition = AgentDefinition(
        name="Agent PMO",
        instructions="Native PMO instructions.",
    )

    root = Path(".")
    # Construct using a tiny on-disk config to exercise the public loader.
    # tmp_path is used in the next test for file validation; here the merge
    # itself is intentionally independent of the provider.
    from agent_dev_kit.project_config import ContextualAgentConfig

    contextual = ContextualAgentConfig(
        key="pmo",
        extra_instructions=("No tocar main sin autorización.",),
    )

    resolved = apply_contextual_config(definition, contextual)

    assert "Native PMO instructions." in resolved.instructions
    assert "No tocar main sin autorización." in resolved.instructions


def test_missing_project_yaml_fails(tmp_path):
    try:
        load_project_config(tmp_path)
    except FileNotFoundError as exc:
        assert "project.yaml" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")
