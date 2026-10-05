import pytest

from agent_dev_kit.git_mutation import GitMutationGateway
from agent_dev_kit.git_policy import (
    GitPolicyGuard,
    GitPolicyViolation,
    GitWorkflowConfig,
    HumanAuthorization,
)


def make_guard(*, verifier=None):
    return GitPolicyGuard(
        GitWorkflowConfig(
            production_branch="main",
            integration_branch="development",
            protected_branches=("main", "development"),
            task_branch_base="development",
            task_pr_target="development",
            release_pr_source="development",
            release_pr_target="main",
        ),
        authorization_verifier=verifier,
    )


def test_gateway_rejects_protected_write_before_executor_runs():
    calls = []

    def executor(operation, arguments):
        calls.append((operation, arguments))
        return "should-not-run"

    gateway = GitMutationGateway(make_guard(), executor)

    with pytest.raises(GitPolicyViolation, match="protected branch"):
        gateway.direct_write("main", payload={"path": "README.md"})

    assert calls == []


def test_gateway_allows_task_branch_only_from_configured_base():
    calls = []

    def executor(operation, arguments):
        calls.append((operation, arguments))
        return "ok"

    gateway = GitMutationGateway(make_guard(), executor)

    result = gateway.create_task_branch(
        "feat/m-031-enforcement",
        base_branch="development",
        issue_reference="M-031",
        base_is_updated=True,
    )

    assert result.operation == "create_task_branch"
    assert calls[0][0] == "create_task_branch"
    assert calls[0][1]["base_branch"] == "development"


def test_gateway_rejects_task_pr_to_main_before_executor_runs():
    calls = []

    def executor(operation, arguments):
        calls.append((operation, arguments))
        return "should-not-run"

    gateway = GitMutationGateway(make_guard(), executor)

    with pytest.raises(GitPolicyViolation, match="must target 'development'"):
        gateway.create_pull_request(
            source_branch="feat/m-031-enforcement",
            target_branch="main",
            purpose="task",
            issue_reference="M-031",
        )

    assert calls == []


def test_gateway_allows_release_pr_development_to_main():
    calls = []

    def executor(operation, arguments):
        calls.append((operation, arguments))
        return {"number": 99}

    gateway = GitMutationGateway(make_guard(), executor)

    result = gateway.create_pull_request(
        source_branch="development",
        target_branch="main",
        purpose="release",
    )

    assert result.result == {"number": 99}
    assert calls[0][1]["purpose"] == "release"


def test_verified_authorization_can_override_specific_direct_write():
    authorization = HumanAuthorization(
        token="approved-token",
        actor="repo-owner",
        scopes=("git:direct_write:main",),
        reason="Explicit emergency override.",
    )

    def verifier(auth, scope):
        return (
            auth.token == "approved-token"
            and auth.actor == "repo-owner"
            and scope in auth.scopes
        )

    calls = []

    def executor(operation, arguments):
        calls.append((operation, arguments))
        return "ok"

    gateway = GitMutationGateway(
        make_guard(verifier=verifier),
        executor,
    )

    gateway.direct_write(
        "main",
        authorization=authorization,
    )

    assert len(calls) == 1
