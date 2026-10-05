from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from agent_dev_kit.git_policy import (
    GitPolicyGuard,
    HumanAuthorization,
)


class GitMutationExecutor(Protocol):
    """Adapter that performs a mutation only after policy validation."""

    def __call__(
        self,
        operation: str,
        arguments: Mapping[str, Any],
    ) -> Any:
        ...


@dataclass(frozen=True, slots=True)
class GitMutationResult:
    operation: str
    result: Any


class GitMutationGateway:
    """Policy-enforced boundary for supported Git write integrations.

    Provider/native tools should call this gateway instead of invoking Git/GitHub
    mutations directly. The gateway validates first and calls the external
    executor only after policy acceptance.
    """

    def __init__(
        self,
        guard: GitPolicyGuard,
        executor: GitMutationExecutor | Callable[[str, Mapping[str, Any]], Any],
    ) -> None:
        self.guard = guard
        self._executor = executor

    def direct_write(
        self,
        branch: str,
        *,
        payload: Mapping[str, Any] | None = None,
        authorization: HumanAuthorization | None = None,
    ) -> GitMutationResult:
        self.guard.validate_direct_write(
            branch,
            authorization=authorization,
        )
        arguments = {
            "branch": branch,
            "payload": dict(payload or {}),
        }
        return GitMutationResult(
            operation="direct_write",
            result=self._executor("direct_write", arguments),
        )

    def create_task_branch(
        self,
        branch: str,
        *,
        base_branch: str,
        issue_reference: str | None = None,
        base_is_updated: bool = True,
        payload: Mapping[str, Any] | None = None,
        authorization: HumanAuthorization | None = None,
    ) -> GitMutationResult:
        self.guard.validate_task_branch_creation(
            branch,
            base_branch=base_branch,
            issue_reference=issue_reference,
            base_is_updated=base_is_updated,
            authorization=authorization,
        )
        arguments = {
            "branch": branch,
            "base_branch": base_branch,
            "issue_reference": issue_reference,
            "base_is_updated": base_is_updated,
            "payload": dict(payload or {}),
        }
        return GitMutationResult(
            operation="create_task_branch",
            result=self._executor("create_task_branch", arguments),
        )

    def create_pull_request(
        self,
        *,
        source_branch: str,
        target_branch: str,
        purpose: str = "task",
        issue_reference: str | None = None,
        payload: Mapping[str, Any] | None = None,
        authorization: HumanAuthorization | None = None,
    ) -> GitMutationResult:
        self.guard.validate_pull_request(
            source_branch=source_branch,
            target_branch=target_branch,
            purpose=purpose,
            issue_reference=issue_reference,
            authorization=authorization,
        )
        arguments = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "purpose": purpose,
            "issue_reference": issue_reference,
            "payload": dict(payload or {}),
        }
        return GitMutationResult(
            operation="create_pull_request",
            result=self._executor("create_pull_request", arguments),
        )
