"""Client-neutral steps shared by the console and MCP Gateway.

No printing, input(), MCP SDK, or model-specific calls live here. Decisions
about whether to continue are made by the trusted host/client boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_dev_kit.git_actions import (
    branch_kind,
    branch_slug,
    current_branch,
    diff_stat,
    is_git_repository,
    issue_reference,
    local_gateway,
    uncommitted_changes,
)
from agent_dev_kit.task_facts import build_facts, verify_verdict
from agent_dev_kit.task_plan import TaskPlan


@dataclass(frozen=True, slots=True)
class ActionPreflight:
    status: str
    reason: str = ""
    issue: str | None = None
    base_branch: str | None = None


def prepare_task_facts(workspace: Any, config: Any, request: str) -> Any:
    """Build facts once; unavailable optional context must not kill the task."""
    if workspace is None:
        return None
    try:
        return build_facts(workspace, config, request)
    except Exception:
        return None


def verify_task_outputs(plan: TaskPlan, workspace: Any) -> None:
    """Deterministically downgrade unsupported acceptance-criterion evidence."""
    if plan.facts is None or workspace is None:
        return
    for node in plan.final_nodes():
        if node.output:
            node.output, _ = verify_verdict(str(node.output), plan.facts, workspace)


def action_preflight(workspace: Any, config: Any, request: str, *, issue: str | None = None) -> ActionPreflight:
    """Apply the same deterministic preflight before CLI or MCP spends tokens.

    The caller collects any missing Issue reference from the person, never
    invents one. The local git verifier performs the actual remote fetch.
    """
    if workspace is None or not is_git_repository(workspace.root):
        return ActionPreflight("not_git_repository", "El proyecto no es un repositorio git.")
    pending = uncommitted_changes(workspace.root)
    if pending:
        return ActionPreflight(
            "dirty_worktree",
            "Hay cambios sin commitear: " + ", ".join(pending[:15]),
        )
    ref = issue or issue_reference(request)
    workflow = config.git_workflow
    if not ref and workflow.require_issue_reference:
        return ActionPreflight("missing_issue", "Falta la referencia de una issue.")
    gateway = local_gateway(workspace.root, workflow)
    base = workflow.task_branch_base
    if not gateway._verifier.branch_exists(base):
        return ActionPreflight(
            "base_missing",
            f"No existe la rama base '{base}'.",
            issue=ref,
            base_branch=base,
        )
    if workflow.require_updated_base_before_task and not gateway._verifier.is_up_to_date(base):
        return ActionPreflight(
            "base_outdated",
            gateway._verifier.reason,
            issue=ref,
            base_branch=base,
        )
    return ActionPreflight("ok", issue=ref, base_branch=base)


def create_action_branch(workspace: Any, config: Any, request: str, *, issue: str | None) -> str:
    """Create a policy-checked task branch; never push or bypass GitPolicyGuard."""
    workflow = config.git_workflow
    gateway = local_gateway(workspace.root, workflow)
    branch = gateway.guard.task_branch_name(
        kind=branch_kind(request),
        issue=(issue or "tarea").lower(),
        slug=branch_slug(request, issue),
    )
    gateway.create_task_branch(
        branch,
        base_branch=workflow.task_branch_base,
        issue_reference=issue,
    )
    return branch


def action_review(workspace: Any, plan: TaskPlan, branch: str) -> dict[str, Any]:
    """Review only: no staging, commits, approvals, or model calls."""
    events = list(workspace.events)
    return {
        "branch": branch,
        "changed_files": uncommitted_changes(workspace.root),
        "diff_stat": diff_stat(workspace.root),
        "commands": [
            event for event in events if event.get("tool") == "run_command"
        ],
        "usage": list(plan.trace.usage) if plan.trace is not None else [],
    }


def commit_action_branch(workspace: Any, config: Any, request: str, *, branch: str, issue: str | None, provider: str, model: str | None) -> str:
    """Commit only after a separately recorded human approval."""
    title = " ".join(request.replace(issue or "\0", " ").split())[:60] if issue else " ".join(request.split())[:60]
    message = f"{issue}: {title}" if issue else title
    message += f"\n\nGenerado con agent-dev-kit /do ({provider} · {model or 'default'})."
    local_gateway(workspace.root, config.git_workflow).direct_write(
        branch, payload={"message": message},
    )
    return message
