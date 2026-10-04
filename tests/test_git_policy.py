import pytest

from agent_dev_kit.git_policy import (
    GitPolicyGuard,
    GitPolicyViolation,
    GitWorkflowConfig,
    git_workflow_from_mapping,
)


def guard() -> GitPolicyGuard:
    return GitPolicyGuard(
        GitWorkflowConfig(
            production_branch="main",
            integration_branch="development",
            protected_branches=("main", "development"),
            task_branch_base="development",
            task_pr_target="development",
            release_pr_source="development",
            release_pr_target="main",
        )
    )


def test_direct_write_to_main_is_blocked():
    with pytest.raises(GitPolicyViolation, match="protected branch"):
        guard().validate_direct_write("main")


def test_direct_write_to_development_is_blocked():
    with pytest.raises(GitPolicyViolation, match="protected branch"):
        guard().validate_direct_write("development")


def test_explicit_human_override_can_allow_protected_write():
    guard().validate_direct_write(
        "main",
        human_override=True,
    )


def test_task_branch_must_start_from_development():
    with pytest.raises(GitPolicyViolation, match="must be created from"):
        guard().validate_task_branch_creation(
            "feat/t-123-report",
            base_branch="main",
            issue_reference="T-123",
        )


def test_task_branch_requires_issue_reference():
    with pytest.raises(GitPolicyViolation, match="Issue reference"):
        guard().validate_task_branch_creation(
            "feat/t-123-report",
            base_branch="development",
        )


def test_task_branch_requires_updated_integration_base():
    with pytest.raises(GitPolicyViolation, match="must be updated"):
        guard().validate_task_branch_creation(
            "feat/t-123-report",
            base_branch="development",
            issue_reference="T-123",
            base_is_updated=False,
        )


def test_task_pr_must_target_development():
    with pytest.raises(GitPolicyViolation, match="must target 'development'"):
        guard().validate_pull_request(
            source_branch="feat/t-123-report",
            target_branch="main",
            purpose="task",
            issue_reference="T-123",
        )


def test_task_pr_from_task_branch_to_development_is_valid():
    guard().validate_pull_request(
        source_branch="feat/t-123-report",
        target_branch="development",
        purpose="task",
        issue_reference="T-123",
    )


def test_release_pr_must_be_development_to_main():
    guard().validate_pull_request(
        source_branch="development",
        target_branch="main",
        purpose="release",
    )

    with pytest.raises(GitPolicyViolation, match="must originate"):
        guard().validate_pull_request(
            source_branch="feat/release",
            target_branch="main",
            purpose="release",
        )


def test_task_branch_name_is_generated_from_policy():
    name = guard().task_branch_name(
        kind="feat",
        issue="T-123",
        slug="Corregir Reporte de Progreso",
    )

    assert name == "feat/t-123-corregir-reporte-de-progreso"


def test_mapping_loads_two_branch_workflow():
    config = git_workflow_from_mapping(
        {
            "branches": {
                "production": "main",
                "integration": "development",
            },
            "protected": ["main", "development"],
            "task_branch": {
                "base": "development",
                "naming": "{kind}/{issue}-{slug}",
            },
            "pull_requests": {
                "task_target": "development",
                "release_source": "development",
                "release_target": "main",
                "require_issue_reference": True,
            },
        }
    )

    assert config.production_branch == "main"
    assert config.integration_branch == "development"
    assert config.protected_branches == ("main", "development")
