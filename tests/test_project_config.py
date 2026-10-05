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


def test_contextual_agent_tools_are_loaded(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example
agents:
  enabled:
    - pmo
""",
    )
    write(
        tmp_path / ".agent-dev-kit" / "agents" / "pmo.yaml",
        """
agent: pmo
tools:
  - github_issues
  - github_pull_requests
""",
    )

    config = load_project_config(tmp_path)

    assert config.agent("pmo").tools == (
        "github_issues",
        "github_pull_requests",
    )


def test_project_preference_file_is_loaded(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example
agents:
  enabled:
    - backend
""",
    )
    write(
        tmp_path / ".agent-dev-kit" / "preferences.yaml",
        """
disabled_global:
  - modular_structure

preferences:
  - id: local_backend_rule
    rule: "Local backend preference."
    agents:
      - backend
""",
    )

    config = load_project_config(tmp_path)

    assert config.preference_config.disabled_global == (
        "modular_structure",
    )
    assert (
        config.preference_config.preferences[0].id
        == "local_backend_rule"
    )


def test_provider_fallbacks_are_loaded(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example

provider:
  name: primary
  default_model: model-a
  fallback_policy: ask
  fallbacks:
    - name: backup
      default_model: model-b

agents:
  enabled:
    - backend
""",
    )

    config = load_project_config(tmp_path)

    assert config.provider.provider == "primary"
    assert config.provider.fallback_policy == "ask"
    assert len(config.provider.fallbacks) == 1
    assert config.provider.fallbacks[0].provider == "backup"
    assert config.provider.fallbacks[0].default_model == "model-b"


def test_git_workflow_is_loaded_and_injected(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example

git_workflow:
  branches:
    production: main
    integration: development
  protected:
    - main
    - development
  task_branch:
    base: development
    naming: "{kind}/{issue}-{slug}"
  pull_requests:
    task_target: development
    release_source: development
    release_target: main
    require_issue_reference: true

agents:
  enabled:
    - pmo
""",
    )

    config = load_project_config(tmp_path)

    assert config.git_workflow.production_branch == "main"
    assert config.git_workflow.integration_branch == "development"
    assert config.git_workflow.task_branch_base == "development"
    assert config.git_workflow.task_pr_target == "development"


def test_orchestration_trace_and_document_templates_are_loaded(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example

orchestration:
  trace:
    enabled: true
    path: .agent-dev-kit/runtime/traces.jsonl
    persist_full_request: false
  improvement_candidate_threshold: 4
  document_templates:
    functional_spec: .agent-dev-kit/templates/functional.md
    technical_spec: .agent-dev-kit/templates/technical.md

agents:
  enabled:
    - triage
    - documentation
""",
    )

    config = load_project_config(tmp_path)

    assert config.orchestration.trace_enabled is True
    assert config.orchestration.persist_full_request is False
    assert config.orchestration.improvement_candidate_threshold == 4
    assert (
        config.orchestration.document_templates["functional_spec"]
        == ".agent-dev-kit/templates/functional.md"
    )
    assert config.project_root == tmp_path


def test_project_orchestration_policies_are_loaded(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example

orchestration:
  policies:
    - id: auth_requires_review
      when:
        any_risk_flags:
          - auth_change
      require_agents:
        - reviewer

agents:
  enabled:
    - triage
    - security
    - reviewer
""",
    )

    config = load_project_config(tmp_path)

    assert len(config.orchestration.policies) == 1
    assert config.orchestration.policies[0].id == "auth_requires_review"
    assert config.orchestration.policies[0].require_agents == ("reviewer",)


def test_project_orchestration_policy_schema_is_validated(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example

orchestration:
  policies:
    - id: invalid_policy
      when:
        any_risk_flags:
          - auth_change
      require_agents:
        - imaginary_agent

agents:
  enabled:
    - triage
""",
    )

    try:
        load_project_config(tmp_path)
    except ValueError as exc:
        assert "imaginary_agent" in str(exc)
    else:
        raise AssertionError("Expected policy schema validation failure")


def test_orchestration_budgets_are_loaded(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example

orchestration:
  budgets:
    max_dag_nodes: 8
    max_provider_calls: 16
    max_revisits: 1
    max_context_chars: 12000
    max_dependency_evidence_chars: 5000

agents:
  enabled:
    - backend
""",
    )

    config = load_project_config(tmp_path)
    budgets = config.orchestration.budgets

    assert budgets.max_dag_nodes == 8
    assert budgets.max_provider_calls == 16
    assert budgets.max_revisits == 1
    assert budgets.max_context_chars == 12000
    assert budgets.max_dependency_evidence_chars == 5000


def test_orchestration_budget_schema_rejects_invalid_values(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: Example

orchestration:
  budgets:
    max_provider_calls: 0

agents:
  enabled:
    - backend
""",
    )

    try:
        load_project_config(tmp_path)
    except ValueError as exc:
        assert "max_provider_calls" in str(exc)
    else:
        raise AssertionError("Expected budget validation failure")
