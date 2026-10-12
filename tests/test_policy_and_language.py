import warnings

import pytest

from agent_dev_kit.git_mutation import GitMutationGateway
from agent_dev_kit.git_policy import (
    GitPolicyGuard,
    GitPolicyViolation,
    GitWorkflowConfig,
)
from agent_dev_kit.project_config import load_project_config
from agent_dev_kit.agent_catalog import build_enabled_definitions
from agent_dev_kit.tooling import ToolRegistry


def gateway(verifier=None):
    calls = []
    guard = GitPolicyGuard(
        GitWorkflowConfig(
            production_branch="main",
            integration_branch="develop",
            protected_branches=("main", "develop"),
            task_branch_base="develop",
            task_pr_target="develop",
            release_pr_source="develop",
        )
    )
    return GitMutationGateway(
        guard,
        lambda op, args: calls.append((op, args)),
        verifier=verifier,
    ), calls


class Verifier:
    def __init__(self, exists=True, updated=True):
        self.exists, self.updated = exists, updated

    def branch_exists(self, branch):
        return self.exists

    def is_up_to_date(self, branch):
        return self.updated


def test_unverified_base_is_rejected_when_policy_requires_update():
    gw, calls = gateway()
    with pytest.raises(GitPolicyViolation, match="Could not verify"):
        gw.create_task_branch("feat/t-1-x", base_branch="develop", issue_reference="T-1")
    assert calls == []


def test_verifier_decides_base_state():
    gw, calls = gateway(Verifier(updated=False))
    with pytest.raises(GitPolicyViolation, match="must be updated"):
        gw.create_task_branch("feat/t-1-x", base_branch="develop", issue_reference="T-1")

    gw, calls = gateway(Verifier(exists=False))
    with pytest.raises(GitPolicyViolation, match="does not exist"):
        gw.create_task_branch("feat/t-1-x", base_branch="develop", issue_reference="T-1")

    gw, calls = gateway(Verifier())
    gw.create_task_branch("feat/t-1-x", base_branch="develop", issue_reference="T-1")
    assert calls[0][0] == "create_task_branch"


def test_generic_registry_rejects_git_mutation_and_warns_on_git_like_keys():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="register_git_mutation"):
        registry.register("push", provider="openai", native=object(), effect="git_mutation")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        registry.register("git_push", provider="openai", native=object())
    assert any("GitPolicyGuard" in str(item.message) for item in caught)
    assert registry.describe()[0]["effect"] == "opaque"


def write_project(tmp_path, project_extra="", agent_yaml=None):
    config_dir = tmp_path / ".agent-dev-kit"
    config_dir.mkdir()
    (config_dir / "project.yaml").write_text(
        "project:\n  name: Demo\n" + project_extra +
        "agents:\n  enabled: [triage, backend, documentation]\n",
        encoding="utf-8",
    )
    if agent_yaml:
        (config_dir / "agents").mkdir()
        (config_dir / "agents" / "documentation.yaml").write_text(agent_yaml, encoding="utf-8")
    return tmp_path


def test_language_rule_is_added_to_every_agent(tmp_path):
    config = load_project_config(write_project(tmp_path, "  language: es\n"))
    definitions = build_enabled_definitions(config)

    assert config.language == "es"
    for definition in definitions.values():
        assert "Spanish (es)" in definition.instructions
        assert "never translate them" in definition.instructions


def test_agent_language_override_and_no_language_keeps_instructions(tmp_path):
    root = write_project(
        tmp_path,
        "  language: es\n",
        agent_yaml="agent: documentation\nlanguage: en\naccess: read_only\n",
    )
    config = load_project_config(root)
    definitions = build_enabled_definitions(config)
    assert "English (en)" in definitions["documentation"].instructions
    assert config.agent("documentation").access == "read_only"


def test_without_language_there_is_no_language_rule(tmp_path):
    config = load_project_config(write_project(tmp_path))
    for definition in build_enabled_definitions(config).values():
        assert "Response language" not in definition.instructions


def test_invalid_language_fails_on_load(tmp_path):
    with pytest.raises(ValueError, match="ISO 639-1"):
        load_project_config(write_project(tmp_path, "  language: castellano\n"))


def test_workspace_config_is_parsed(tmp_path):
    config = load_project_config(
        write_project(
            tmp_path,
            "",
        )
    )
    assert config.workspace.test_commands == ()


def test_every_agent_knows_who_designed_the_framework(tmp_path):
    config = load_project_config(write_project(tmp_path))
    for definition in build_enabled_definitions(config).values():
        assert "designed by sr.macros@gmail.com" in definition.instructions
