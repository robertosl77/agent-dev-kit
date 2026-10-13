from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping, Protocol


class GitPolicyViolation(RuntimeError):
    """Raised before a Git mutation that violates the configured workflow."""


@dataclass(frozen=True, slots=True)
class HumanAuthorization:
    """Opaque, scoped authorization supplied by a trusted human-facing layer."""

    token: str
    actor: str
    scopes: tuple[str, ...]
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.token.strip():
            raise ValueError("HumanAuthorization.token cannot be empty.")
        if not self.actor.strip():
            raise ValueError("HumanAuthorization.actor cannot be empty.")
        if not self.scopes:
            raise ValueError("HumanAuthorization.scopes cannot be empty.")


class HumanAuthorizationVerifier(Protocol):
    def __call__(
        self,
        authorization: HumanAuthorization,
        action_scope: str,
    ) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class GitWorkflowConfig:
    production_branch: str = "main"
    integration_branch: str = "development"
    protected_branches: tuple[str, ...] = ("main", "development")
    task_branch_base: str = "development"
    task_branch_naming: str = "{kind}/{issue}-{slug}"
    task_pr_target: str = "development"
    release_pr_source: str = "development"
    release_pr_target: str = "main"
    require_issue_reference: bool = True
    require_updated_base_before_task: bool = True
    allow_explicit_human_override: bool = True

    def __post_init__(self) -> None:
        required = {
            "production_branch": self.production_branch,
            "integration_branch": self.integration_branch,
            "task_branch_base": self.task_branch_base,
            "task_pr_target": self.task_pr_target,
            "release_pr_source": self.release_pr_source,
            "release_pr_target": self.release_pr_target,
        }
        for name, value in required.items():
            if not value.strip():
                raise ValueError(f"git_workflow.{name} cannot be empty.")

        if self.task_branch_base != self.integration_branch:
            raise ValueError(
                "git_workflow.task_branch_base must match integration_branch "
                "for the v0.1.0 workflow."
            )
        if self.task_pr_target != self.integration_branch:
            raise ValueError(
                "git_workflow.task_pr_target must match integration_branch."
            )
        if self.release_pr_source != self.integration_branch:
            raise ValueError(
                "git_workflow.release_pr_source must match integration_branch."
            )
        if self.release_pr_target != self.production_branch:
            raise ValueError(
                "git_workflow.release_pr_target must match production_branch."
            )

        protected = {normalize_branch(item) for item in self.protected_branches}
        if normalize_branch(self.production_branch) not in protected:
            raise ValueError(
                "git_workflow.protected_branches must include production_branch."
            )
        if normalize_branch(self.integration_branch) not in protected:
            raise ValueError(
                "git_workflow.protected_branches must include integration_branch."
            )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "branches": {
                "production": self.production_branch,
                "integration": self.integration_branch,
            },
            "protected": list(self.protected_branches),
            "task_branch": {
                "base": self.task_branch_base,
                "naming": self.task_branch_naming,
            },
            "pull_requests": {
                "task_target": self.task_pr_target,
                "release_source": self.release_pr_source,
                "release_target": self.release_pr_target,
                "require_issue_reference": self.require_issue_reference,
            },
            "sync": {
                "require_updated_base_before_task": (
                    self.require_updated_base_before_task
                )
            },
            "direct_writes": {
                "protected_branches": "deny",
                "exception": (
                    "explicit_human_authorization"
                    if self.allow_explicit_human_override
                    else "none"
                ),
            },
        }


class GitPolicyGuard:
    """Deterministic gate for Git mutations performed by integrations."""

    def __init__(
        self,
        config: GitWorkflowConfig,
        *,
        authorization_verifier: HumanAuthorizationVerifier
        | Callable[[HumanAuthorization, str], bool]
        | None = None,
    ) -> None:
        self.config = config
        self._authorization_verifier = authorization_verifier
        self._protected = {
            normalize_branch(item) for item in config.protected_branches
        }

    def validate_direct_write(
        self,
        branch: str,
        *,
        authorization: HumanAuthorization | None = None,
    ) -> None:
        normalized = normalize_branch(branch)
        action_scope = self.direct_write_scope(branch)
        if normalized in self._protected and not self._override_allowed(
            authorization,
            action_scope,
        ):
            raise GitPolicyViolation(
                f"Direct write to protected branch '{branch}' is forbidden. "
                "Create a task branch or use an explicit human override."
            )

    def validate_task_branch_creation(
        self,
        branch: str,
        *,
        base_branch: str,
        issue_reference: str | None = None,
        base_is_updated: bool | None = None,
        authorization: HumanAuthorization | None = None,
    ) -> None:
        """Validate a task branch creation.

        ``base_is_updated`` must come from a real check of the repository
        (see ``RepositoryStateVerifier`` in git_mutation). ``None`` means it
        was not verified, which is rejected when the policy requires an
        updated base (M-063).
        """

        action_scope = self.task_branch_scope(branch)
        if self._override_allowed(authorization, action_scope):
            return

        if normalize_branch(branch) in self._protected:
            raise GitPolicyViolation(
                f"Task branch '{branch}' cannot be a protected branch."
            )

        if normalize_branch(base_branch) != normalize_branch(
            self.config.task_branch_base
        ):
            raise GitPolicyViolation(
                f"Task branch '{branch}' must be created from "
                f"'{self.config.task_branch_base}', not '{base_branch}'."
            )

        if (
            self.config.require_issue_reference
            and not (issue_reference or "").strip()
        ):
            raise GitPolicyViolation(
                "Task branch creation requires an Issue reference."
            )

        if self.config.require_updated_base_before_task:
            if base_is_updated is None:
                raise GitPolicyViolation(
                    f"Could not verify that base branch '{base_branch}' is "
                    "updated. Provide a repository state verifier."
                )
            if not base_is_updated:
                raise GitPolicyViolation(
                    f"Base branch '{base_branch}' must be updated before "
                    "creating a task branch."
                )

    def validate_pull_request(
        self,
        *,
        source_branch: str,
        target_branch: str,
        purpose: str = "task",
        issue_reference: str | None = None,
        authorization: HumanAuthorization | None = None,
    ) -> None:
        action_scope = self.pull_request_scope(
            source_branch=source_branch,
            target_branch=target_branch,
            purpose=purpose,
        )
        if self._override_allowed(authorization, action_scope):
            return

        purpose_key = purpose.strip().lower()

        if purpose_key == "task":
            if normalize_branch(target_branch) != normalize_branch(
                self.config.task_pr_target
            ):
                raise GitPolicyViolation(
                    f"Task PR must target '{self.config.task_pr_target}', "
                    f"not '{target_branch}'."
                )
            if normalize_branch(source_branch) in self._protected:
                raise GitPolicyViolation(
                    "Task PR source must be a task branch, not a protected "
                    f"branch ('{source_branch}')."
                )
            if (
                self.config.require_issue_reference
                and not (issue_reference or "").strip()
            ):
                raise GitPolicyViolation(
                    "Task PR requires an Issue reference."
                )
            return

        if purpose_key == "release":
            if normalize_branch(source_branch) != normalize_branch(
                self.config.release_pr_source
            ):
                raise GitPolicyViolation(
                    "Release PR must originate from "
                    f"'{self.config.release_pr_source}'."
                )
            if normalize_branch(target_branch) != normalize_branch(
                self.config.release_pr_target
            ):
                raise GitPolicyViolation(
                    "Release PR must target "
                    f"'{self.config.release_pr_target}'."
                )
            return

        raise GitPolicyViolation(
            f"Unknown pull request purpose '{purpose}'."
        )

    def task_branch_name(
        self,
        *,
        kind: str,
        issue: str,
        slug: str,
    ) -> str:
        values = {
            "kind": _sanitize_segment(kind),
            "issue": _sanitize_segment(issue),
            "slug": _sanitize_slug(slug),
        }
        try:
            rendered = self.config.task_branch_naming.format(**values)
        except KeyError as exc:
            raise ValueError(
                "task_branch_naming may only use {kind}, {issue}, and {slug}."
            ) from exc
        return rendered.strip("/")

    @staticmethod
    def direct_write_scope(branch: str) -> str:
        return f"git:direct_write:{normalize_branch(branch)}"

    @staticmethod
    def task_branch_scope(branch: str) -> str:
        return f"git:create_task_branch:{normalize_branch(branch)}"

    @staticmethod
    def pull_request_scope(
        *,
        source_branch: str,
        target_branch: str,
        purpose: str,
    ) -> str:
        return (
            "git:create_pull_request:"
            f"{purpose.strip().lower()}:"
            f"{normalize_branch(source_branch)}->"
            f"{normalize_branch(target_branch)}"
        )

    def _override_allowed(
        self,
        authorization: HumanAuthorization | None,
        action_scope: str,
    ) -> bool:
        if not self.config.allow_explicit_human_override:
            return False
        if authorization is None:
            return False
        if action_scope not in authorization.scopes:
            return False
        if self._authorization_verifier is None:
            return False
        return bool(
            self._authorization_verifier(
                authorization,
                action_scope,
            )
        )


def git_workflow_from_mapping(data: Mapping[str, Any] | None) -> GitWorkflowConfig:
    if not data:
        return GitWorkflowConfig()
    if not isinstance(data, Mapping):
        raise ValueError("'git_workflow' must be a mapping.")

    branches = data.get("branches") or {}
    task_branch = data.get("task_branch") or {}
    pull_requests = data.get("pull_requests") or {}
    sync = data.get("sync") or {}
    direct_writes = data.get("direct_writes") or {}

    for name, value in (
        ("branches", branches),
        ("task_branch", task_branch),
        ("pull_requests", pull_requests),
        ("sync", sync),
        ("direct_writes", direct_writes),
    ):
        if not isinstance(value, Mapping):
            raise ValueError(f"'git_workflow.{name}' must be a mapping.")

    production = str(branches.get("production") or "main").strip()
    integration = str(
        branches.get("integration") or "development"
    ).strip()

    protected_raw = data.get("protected")
    if protected_raw is None:
        protected = (production, integration)
    else:
        if not isinstance(protected_raw, list):
            raise ValueError("'git_workflow.protected' must be a list.")
        protected = tuple(
            str(item).strip()
            for item in protected_raw
            if str(item).strip()
        )

    exception = str(
        direct_writes.get("exception") or "explicit_human_authorization"
    ).strip().lower()

    return GitWorkflowConfig(
        production_branch=production,
        integration_branch=integration,
        protected_branches=protected,
        task_branch_base=str(
            task_branch.get("base") or integration
        ).strip(),
        task_branch_naming=str(
            task_branch.get("naming") or "{kind}/{issue}-{slug}"
        ).strip(),
        task_pr_target=str(
            pull_requests.get("task_target") or integration
        ).strip(),
        release_pr_source=str(
            pull_requests.get("release_source") or integration
        ).strip(),
        release_pr_target=str(
            pull_requests.get("release_target") or production
        ).strip(),
        require_issue_reference=bool(
            pull_requests.get("require_issue_reference", True)
        ),
        require_updated_base_before_task=bool(
            sync.get("require_updated_base_before_task", True)
        ),
        allow_explicit_human_override=(
            exception == "explicit_human_authorization"
        ),
    )


def normalize_branch(value: str) -> str:
    return value.strip().removeprefix("refs/heads/")


def _sanitize_segment(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return sanitized.strip("-").lower()


def _sanitize_slug(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", value.strip())
    return re.sub(r"-+", "-", sanitized).strip("-").lower()
