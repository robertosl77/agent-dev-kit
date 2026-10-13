"""Resumable, provider-neutral task workflows for MCP and other hosts.

The workflow runs the *same* DevAgentKit, Workspace, TaskFacts and Git gateways
as the CLI. Each approval is task+stage+nonce-scoped and single-use. A trusted
human-facing MCP host must confirm the decision before invoking decide().
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from threading import RLock
import os
from time import monotonic
from typing import Any
from uuid import uuid4

from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.git_actions import current_branch, is_git_repository
from agent_dev_kit.orchestration import OrchestrationTraceStore, resolve_project_trace_path
from agent_dev_kit.graph_analysis import graph_rows, analysis_report
from agent_dev_kit.provider_errors import ProviderError, ProviderRecoverableError
from agent_dev_kit.task_plan import TaskPlan
from agent_dev_kit.task_workflow import (
    action_preflight,
    action_review,
    commit_action_branch,
    create_action_branch,
    prepare_task_facts,
    verify_task_outputs,
)
from agent_dev_kit.workspace_tools import Workspace
from agent_dev_kit.workflow_checkpoint import (
    WorkflowCheckpointStore, encode_plan, decode_plan,
)


STAGES = frozenset({"plan", "propose", "act"})
FINISHED = frozenset({
    "completed", "rejected", "canceled", "failed", "blocked",
    "manual_review_required",
})


def serialized(method):
    """Serialize each approval and its side effects in one server process."""

    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return guarded


@dataclass(slots=True)
class WorkflowState:
    request: str
    mode: str
    runtime: ProviderRuntime
    workspace: Workspace
    created_at: float
    last_accessed_at: float
    issue: str | None = None
    phase: str = "new"
    status: str = "pending"
    plan: TaskPlan | None = None
    branch: str | None = None
    review: dict[str, Any] | None = None
    pending_decision: dict[str, Any] | None = None
    pending_error: ProviderRecoverableError | None = None
    failure: str | None = None


class WorkflowController:
    """One fixed-repository workflow facade: no raw shell, Git or model access."""

    def __init__(self, gateway: Any, *, allow_actions: bool = False, clock: Any = None):
        self.gateway = gateway
        self.allow_actions = allow_actions
        self._clock = clock or monotonic
        self._sessions: dict[str, WorkflowState] = {}
        self._lock = RLock()
        self._store = WorkflowCheckpointStore(gateway.project_root)

    @serialized
    def start(self, request: str, mode: str = "propose", issue: str | None = None) -> dict[str, Any]:
        mode = str(mode).strip().lower()
        if mode not in STAGES:
            raise ValueError("mode must be plan, propose, or act.")
        if mode == "act" and not self.allow_actions:
            return {"status": "blocked", "reason": "MCP writes are disabled by the server owner."}
        if not request.strip():
            raise ValueError("request cannot be empty.")
        self.cleanup()
        # Exactly one active action workflow may own this worktree.
        if mode == "act":
            for ident, existing in self._sessions.items():
                if existing.mode == "act" and existing.status not in FINISHED:
                    return {
                        "status": "blocked",
                        "reason": "Another action workflow owns the repository worktree.",
                        "workflow_id": ident,
                    }
            if self._store.has_active_action(self.gateway.config.gateway.session_ttl_seconds):
                return {
                    "status": "blocked",
                    "reason": "An unfinished action checkpoint already owns this project.",
                }
        config = self.gateway.config
        maximum = config.gateway.max_sessions
        if len(self._sessions) + len(self.gateway._conversations) + len(self.gateway._tasks) >= maximum:
            raise RuntimeError("Gateway session limit reached.")
        root = self.gateway.project_root
        workspace, runtime = self._new_runtime(mode)
        ident = "workflow_" + uuid4().hex
        now = self._clock()
        state = WorkflowState(
            request=request.strip(), mode=mode, runtime=runtime,
            workspace=workspace, issue=(issue or "").strip().lstrip("#") or None,
            created_at=now, last_accessed_at=now,
        )
        self._sessions[ident] = state
        return self._drive(ident, state)

    def _new_runtime(self, mode: str) -> tuple[Workspace, ProviderRuntime]:
        config = self.gateway.config
        workspace = Workspace(
            root=self.gateway.project_root,
            config=config.workspace,
            approve_command=lambda command: False,
            defer_commands=(mode == "act"),
        )
        workspace._github_token = os.environ.get("AGENT_DEV_KIT_GITHUB_READ_TOKEN") or None
        runtime = ProviderRuntime(
            registry=self.gateway.registry,
            project_config=config,
            tool_registry=self.gateway.tool_registry,
            preference_profile=self.gateway.preference_profile,
            workspace=workspace,
            mode="propose",
        )
        return workspace, runtime

    def _persist(self, ident: str, state: WorkflowState) -> None:
        """Save at every external boundary, never provider credentials."""
        self._store.save(ident, {
            "request": state.request,
            "mode": state.mode,
            "phase": state.phase,
            "status": state.status,
            "issue": state.issue,
            "branch": state.branch,
            "failure": state.failure,
            "plan": encode_plan(state.plan),
            "review": state.review,
            "pending_decision": state.pending_decision,
            "pending_commands": list(state.workspace.pending_commands),
            "command_outcomes": list(state.workspace.events),
            "target_index": state.runtime._target_index,
        })

    def _restore(self, ident: str) -> WorkflowState | None:
        data = self._store.load(ident, self.gateway.config.gateway.session_ttl_seconds)
        if data is None:
            return None
        workspace, runtime = self._new_runtime(str(data["mode"]))
        runtime._target_index = min(
            max(int(data.get("target_index", 0)), 0),
            len(runtime.project_config.provider.targets()) - 1,
        )
        now = self._clock()
        state = WorkflowState(
            request=data["request"], mode=data["mode"], runtime=runtime,
            workspace=workspace, issue=data.get("issue"),
            created_at=now, last_accessed_at=now,
            phase=data["phase"], status=data["status"],
            plan=decode_plan(data.get("plan")),
            branch=data.get("branch"), review=data.get("review"),
            failure=data.get("failure"),
        )
        workspace.pending_commands.extend(data.get("pending_commands") or [])
        workspace.events.extend(data.get("command_outcomes") or [])
        if state.pending_decision:
            state.pending_decision = None
        pending = data.get("pending_decision")
        if pending is not None and state.status == "approval_required":
            # Old approval IDs are invalid across process boundaries.
            state.pending_decision = {**pending, "id": uuid4().hex}
        if state.status in {
            "planning", "executing_intake", "executing",
            "fallback_required", "executing_command", "committing", "branch_creation",
        }:
            state.status = "interrupted"
            state.failure = (
                "Execution was interrupted. No model call or write will be "
                "automatically replayed."
            )
        self._sessions[ident] = state
        self._persist(ident, state)
        return state

    @serialized
    def resume(self, workflow_id: str, approve: bool) -> dict[str, Any]:
        """Explicit retry of safe phases, never of interrupted action writes."""
        state = self._state(workflow_id)
        if state.status != "interrupted" or type(approve) is not bool:
            raise ValueError("No interrupted workflow awaiting recovery.")
        if state.mode == "act" and not self.allow_actions:
            raise ValueError("MCP action mode is disabled by the server owner.")
        if not approve:
            return self.cancel(workflow_id)
        if state.mode == "act" and state.phase in {
            "execute", "command_execution", "commit_execution", "branch_creation",
        }:
            state.status, state.phase = "manual_review_required", "manual_review_required"
            state.failure = (
                "Action run was interrupted after branch creation; inspect the "
                "worktree and commit manually. Never replay writes automatically."
            )
            return self._snapshot(workflow_id, state)
        if state.phase == "planning":
            state.plan = None
        if state.plan is not None:
            # Non-completed model calls have no durable transcript; never
            # pretend that a running node completed.
            for node in state.plan.nodes:
                if node.status == "running":
                    node.status = "pending"
        if state.phase == "intake" and state.plan is not None:
            if state.plan.requires_story_approval and all(
                node.status == "completed" for node in state.plan.nodes
                if node.agent == "scrum_master"
            ):
                state.phase = "story_confirmation"
                story = next(
                    node.output for node in state.plan.nodes
                    if node.agent == "scrum_master"
                )
                return self._require(
                    workflow_id, state, "story",
                    "¿Confirmás la historia de usuario y sus criterios?",
                    details=story,
                )
        if state.phase not in {"planning", "intake", "execute"}:
            state.phase = "planning" if state.plan is None else "intake"
        # No automatic repetition: an explicit human approval starts the retry.
        return self._drive(workflow_id, state)

    @serialized
    def status(self, workflow_id: str) -> dict[str, Any]:
        return self._snapshot(workflow_id, self._state(workflow_id))

    @serialized
    def decide(self, workflow_id: str, decision_id: str, approve: bool) -> dict[str, Any]:
        state = self._state(workflow_id)
        if state.mode == "act" and not self.allow_actions:
            raise ValueError("MCP action mode is disabled by the server owner.")
        pending = state.pending_decision
        if pending is None or pending["id"] != decision_id:
            raise ValueError("There is no matching outstanding decision.")
        if type(approve) is not bool:
            raise ValueError("approve must be a boolean.")
        kind = pending["kind"]
        state.pending_decision = None   # consume: no replay or permanent approval
        if not approve:
            state.status = "rejected"
            state.phase = "rejected"
            if kind == "command":
                state.failure = "Restricted command rejected; action validation is incomplete."
            if state.plan is not None and kind == "story":
                state.runtime.kit.record_story_rejected(state.plan)
            return self._snapshot(workflow_id, state)
        if kind == "command":
            assert state.plan is not None and state.branch is not None
            if not state.workspace.pending_commands:
                raise ValueError("No pending command exists.")
            entry = state.workspace.pending_commands[0]
            if entry != pending["details"]:
                raise ValueError("Command request changed since approval.")
            # Don't authorize a command if a different checkout was selected.
            if current_branch(state.workspace.root) != state.branch:
                state.status, state.phase = "blocked", "blocked"
                state.failure = "Git branch changed before restricted command approval."
                return self._snapshot(workflow_id, state)
            try:
                state.phase, state.status = "command_execution", "executing_command"
                self._persist(workflow_id, state)
                result = state.workspace.execute_pending_command(entry)
            except Exception as exc:
                state.status, state.phase = "blocked", "blocked"
                state.failure = f"Approved command could not run: {exc}"
                return self._snapshot(workflow_id, state)
            if not result.startswith("exit code 0"):
                state.status, state.phase = "blocked", "blocked"
                state.failure = f"Approved command failed: {result[:600]}"
                return self._snapshot(workflow_id, state)
            if state.workspace.pending_commands:
                return self._next_command_approval(workflow_id, state)
            return self._finish_action(workflow_id, state)
        if kind == "plan":
            state.phase = "intake"
        elif kind == "story":
            assert state.plan is not None
            state.plan.story_approved = True
            state.phase = "execute"
        elif kind == "branch":
            state.phase = "planning"
        elif kind == "commit":
            assert state.branch is not None and state.plan is not None
            try:
                # An approval applies to exactly the code that was reviewed.
                latest = action_review(state.workspace, state.plan, state.branch)
                if latest["fingerprint"] != state.review["fingerprint"]:
                    state.review = latest
                    state.phase = "commit_confirmation"
                    return self._require(
                        workflow_id, state, "commit",
                        "Los archivos cambiaron desde la revisión. ¿Aprobás el nuevo diff?",
                        details=latest,
                    )
                if not latest["diff_complete"]:
                    state.status, state.phase = "blocked", "blocked"
                    state.failure = "Diff too large for safe MCP approval; review and commit locally."
                    return self._snapshot(workflow_id, state)
                state.phase, state.status = "commit_execution", "committing"
                self._persist(workflow_id, state)
                commit_action_branch(
                    state.workspace, self.gateway.config, state.request,
                    branch=state.branch, issue=state.issue,
                    provider=state.runtime.current_target.provider,
                    model=self.gateway.config.provider.default_model,
                )
            except Exception as exc:
                state.status, state.phase, state.failure = "failed", "failed", str(exc)
                return self._snapshot(workflow_id, state)
            state.status, state.phase = "completed", "completed"
            return self._snapshot(workflow_id, state)
        else:
            raise ValueError("Unsupported workflow decision.")
        return self._drive(workflow_id, state)

    @serialized
    def provide_issue(self, workflow_id: str, issue: str) -> dict[str, Any]:
        state = self._state(workflow_id)
        if state.mode == "act" and not self.allow_actions:
            raise ValueError("MCP action mode is disabled by the server owner.")
        if state.phase != "issue_required" or not issue.strip():
            raise ValueError("No issue reference is currently required.")
        state.issue = issue.strip().lstrip("#")
        state.phase = "new"
        return self._drive(workflow_id, state)

    @serialized
    def fallback(self, workflow_id: str, approve: bool) -> dict[str, Any]:
        state = self._state(workflow_id)
        if state.mode == "act" and not self.allow_actions:
            raise ValueError("MCP action mode is disabled by the server owner.")
        if type(approve) is not bool:
            raise ValueError("approve must be a boolean.")
        if state.pending_error is None or state.status != "fallback_required":
            raise ValueError("No fallback is pending for this workflow.")
        error = state.pending_error
        state.pending_error = None
        if not approve:
            state.status, state.phase = "rejected", "rejected"
            return self._snapshot(workflow_id, state)
        state.runtime.switch_after_error(
            error,
            confirm_switch=lambda current, next_target, cause: True,
        )
        return self._drive(workflow_id, state)

    @serialized
    def cancel(self, workflow_id: str) -> dict[str, Any]:
        state = self._state(workflow_id)
        if state.status in FINISHED:
            return self._snapshot(workflow_id, state)
        state.pending_decision = None
        state.pending_error = None
        state.status, state.phase = "canceled", "canceled"
        # Local changes are NEVER silently reset or discarded.
        return self._snapshot(workflow_id, state)

    @serialized
    def usage(self, workflow_id: str) -> dict[str, Any]:
        """Report provider/model call usage without exposing provider secrets."""
        from agent_dev_kit.usage import total_tokens, estimate_cost

        state = self._state(workflow_id)
        records = (
            list(state.plan.trace.usage)
            if state.plan is not None and state.plan.trace is not None
            else []
        )
        return {
            "workflow_id": workflow_id,
            "by_call": records,
            "totals": total_tokens(records),
            "estimated_usd": estimate_cost(records, self.gateway.config.pricing),
        }

    def repository_status(self) -> dict[str, Any]:
        from agent_dev_kit.git_actions import diff_stat, uncommitted_changes
        root = self.gateway.project_root
        return {
            "repository": root.name,
            "git": is_git_repository(root),
            "branch": current_branch(root) if is_git_repository(root) else None,
            "dirty_files": uncommitted_changes(root) if is_git_repository(root) else [],
            "diff_stat": diff_stat(root) if is_git_repository(root) else "",
        }

    def graphs(self, limit: int = 20) -> dict[str, Any]:
        config = self.gateway.config
        path = resolve_project_trace_path(self.gateway.project_root, config.orchestration.trace_path)
        traces = OrchestrationTraceStore(path).read()
        rows = graph_rows(traces)[-max(min(int(limit), 100), 1):]
        return {"runs": [
            {
                "recorded_at": r.recorded_at, "mode": r.mode, "status": r.status,
                "classification": r.classification, "model": r.model,
                "agents": list(r.agents), "nodes": r.nodes,
                "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            }
            for r in rows
        ]}

    def candidates(self) -> dict[str, Any]:
        config = self.gateway.config
        path = resolve_project_trace_path(self.gateway.project_root, config.orchestration.trace_path)
        traces = OrchestrationTraceStore(path).read()
        return {"report": analysis_report(
            traces, threshold=config.orchestration.improvement_candidate_threshold
        )}

    def _drive(self, ident: str, state: WorkflowState) -> dict[str, Any]:
        try:
            return self._run_stages(ident, state)
        except ProviderRecoverableError as exc:
            response = self.gateway._fallback_response(
                exc, state.runtime, workflow_id=ident, stage=state.phase,
            )
            if response["status"] == "fallback_required":
                state.pending_error = exc
                state.status = "fallback_required"
            else:
                state.status, state.phase = "failed", "failed"
                state.failure = response["message"]
            return self._snapshot(ident, state, fallback=response)
        except Exception as exc:
            state.status, state.phase, state.failure = "failed", "failed", str(exc)
            return self._snapshot(ident, state)

    def _run_stages(self, ident: str, state: WorkflowState) -> dict[str, Any]:
        config = self.gateway.config
        while True:
            if state.phase == "new":
                if state.mode == "act":
                    check = action_preflight(
                        state.workspace, config, state.request, issue=state.issue,
                    )
                    if check.status == "missing_issue":
                        state.phase, state.status = "issue_required", "input_required"
                        return self._snapshot(ident, state)
                    if check.status != "ok":
                        state.phase, state.status, state.failure = "blocked", "blocked", check.reason
                        return self._snapshot(ident, state)
                    state.issue = check.issue
                elif state.mode == "propose" and is_git_repository(state.workspace.root):
                    branch = current_branch(state.workspace.root)
                    if branch and branch != config.git_workflow.integration_branch:
                        state.phase = "branch_confirmation"
                        return self._require(
                            ident, state, "branch",
                            "La rama actual es " + branch + ". ¿Analizar su contenido?",
                        )
                state.phase = "planning"
            if state.phase == "planning":
                state.status = "planning"
                self._persist(ident, state)
                state.plan = state.runtime.kit.plan_task_sync(state.request)
                if state.mode == "plan":
                    state.plan.trace.mode = "plan"
                    state.runtime.kit.record_plan_only(state.plan)
                    state.status, state.phase = "completed", "completed"
                    return self._snapshot(ident, state)
                if state.mode == "act":
                    state.phase = "plan_confirmation"
                    return self._require(ident, state, "plan", "¿Ejecutar este plan?")
                state.phase = "intake"
            if state.phase == "intake":
                assert state.plan is not None
                state.plan.facts = prepare_task_facts(state.workspace, config, state.request)
                state.workspace.bind_trace(state.plan.trace)
                state.plan.on_checkpoint = lambda _: self._persist(ident, state)
                if state.plan.requires_story_approval:
                    state.status = "executing_intake"
                    self._persist(ident, state)
                    state.runtime.kit.execute_plan_sync(state.plan, intake_only=True)
                    state.phase = "story_confirmation"
                    story = next(node.output for node in state.plan.nodes if node.agent == "scrum_master")
                    return self._require(
                        ident, state, "story",
                        "¿Confirmás la historia de usuario y sus criterios?",
                        details=story,
                    )
                state.phase = "execute"
            if state.phase == "execute":
                assert state.plan is not None
                if state.mode == "act" and state.branch is None:
                    # Re-check just before mutation: branch/worktree may have
                    # changed during human review of the plan or story.
                    check = action_preflight(
                        state.workspace, config, state.request, issue=state.issue,
                    )
                    if check.status != "ok":
                        state.status, state.phase, state.failure = "blocked", "blocked", check.reason
                        return self._snapshot(ident, state)
                    state.status, state.phase = "branch_creation", "branch_creation"
                    self._persist(ident, state)
                    state.branch = create_action_branch(
                        state.workspace, config, state.request, issue=state.issue,
                    )
                    state.phase = "execute"
                    self._persist(ident, state)
                    state.runtime = state.runtime.with_mode("act")
                    if state.plan.trace is not None:
                        state.plan.trace.mode = "act"
                state.status = "executing"
                self._persist(ident, state)
                state.workspace.bind_trace(state.plan.trace)
                state.plan.on_checkpoint = lambda _: self._persist(ident, state)
                state.plan.facts = prepare_task_facts(state.workspace, config, state.request)
                state.runtime.kit.execute_plan_sync(state.plan)
                if state.mode == "act":
                    if state.workspace.pending_commands:
                        state.phase = "command_confirmation"
                        return self._next_command_approval(ident, state)
                    return self._finish_action(ident, state)
                verify_task_outputs(state.plan, state.workspace)
                state.status, state.phase = "completed", "completed"
                return self._snapshot(ident, state)
            if state.phase in FINISHED or state.phase in {
                "issue_required", "branch_confirmation", "plan_confirmation",
                "story_confirmation", "commit_confirmation",
                "command_confirmation", "manual_review_required",
            }:
                return self._snapshot(ident, state)
            raise RuntimeError("Unsupported workflow phase: " + state.phase)

    def _finish_action(self, ident: str, state: WorkflowState) -> dict[str, Any]:
        assert state.plan is not None and state.branch is not None
        verify_task_outputs(state.plan, state.workspace)
        state.review = action_review(state.workspace, state.plan, state.branch)
        if not state.review["changed_files"]:
            state.status, state.phase = "completed", "completed"
            return self._snapshot(ident, state)
        if not state.review["diff_complete"]:
            state.status, state.phase = "blocked", "blocked"
            state.failure = "Diff too large for safe MCP approval; review and commit locally."
            return self._snapshot(ident, state)
        state.phase = "commit_confirmation"
        return self._require(
            ident, state, "commit",
            "¿Aprobás el commit local del diff completo revisado?",
            details=state.review,
        )

    def _next_command_approval(self, ident: str, state: WorkflowState) -> dict[str, Any]:
        entry = state.workspace.pending_commands[0]
        state.phase = "command_confirmation"
        return self._require(
            ident, state, "command",
            "¿Autorizás ejecutar este comando restringido, una sola vez?",
            details=dict(entry),
        )

    def _require(
        self, ident: str, state: WorkflowState, kind: str,
        prompt: str, *, details: Any = None,
    ) -> dict[str, Any]:
        state.status = "approval_required"
        state.pending_decision = {
            "id": uuid4().hex,
            "kind": kind,
            "prompt": prompt,
            "details": details,
        }
        return self._snapshot(ident, state)

    def _state(self, ident: str) -> WorkflowState:
        self.cleanup()
        state = self._sessions.get(ident)
        if state is None:
            state = self._restore(ident)
        if state is None:
            raise ValueError("Unknown or expired workflow session.")
        state.last_accessed_at = self._clock()
        return state

    def cleanup(self) -> int:
        now = self._clock()
        ttl = self.gateway.config.gateway.session_ttl_seconds
        expired = [ident for ident, s in self._sessions.items() if now - s.last_accessed_at >= ttl]
        for ident in expired:
            del self._sessions[ident]
            self._store.delete(ident)
        return len(expired)

    def _snapshot(
        self, ident: str, state: WorkflowState, *, fallback: Any = None,
    ) -> dict[str, Any]:
        state.last_accessed_at = self._clock()
        self._persist(ident, state)
        plan = state.plan
        return {
            "workflow_id": ident, "status": state.status,
            "mode": state.mode, "phase": state.phase,
            "issue": state.issue, "branch": state.branch,
            "provider": state.runtime.current_target.provider,
            "plan": self.gateway._plan_payload(plan),
            "approval": state.pending_decision,
            "review": state.review, "failure": state.failure,
            "input_required": "issue" if state.phase == "issue_required" else None,
            "fallback": fallback,
            "recovery": "manual_review_only" if state.status == "manual_review_required"
                else ("explicit_resume_required" if state.status == "interrupted" else None),
        }
