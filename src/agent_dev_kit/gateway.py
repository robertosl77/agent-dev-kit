from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.orchestration_budget import OrchestrationBudgetExceeded
from agent_dev_kit.preferences import PreferenceProfile
from agent_dev_kit.project_config import (
    ProjectAgentDevKitConfig,
    load_project_config,
)
from agent_dev_kit.provider_errors import (
    ProviderError,
    ProviderFallbackRequired,
    ProviderRecoverableError,
)
from agent_dev_kit.provider_registry import (
    ProviderRegistry,
    build_default_registry,
)
from agent_dev_kit.runtime import DevConversation
from agent_dev_kit.task_plan import TaskPlan
from agent_dev_kit.tooling import ToolRegistry


class TaskGatewayStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    FALLBACK_PENDING = "fallback_pending"
    BLOCKED = "blocked"
    FAILED = "failed"
    REQUIRES_HUMAN_APPROVAL = "requires_human_approval"
    COMPLETED = "completed"


_TERMINAL_TASK_STATUSES = frozenset(
    {
        TaskGatewayStatus.BLOCKED,
        TaskGatewayStatus.FAILED,
        TaskGatewayStatus.REQUIRES_HUMAN_APPROVAL,
        TaskGatewayStatus.COMPLETED,
    }
)


@dataclass(slots=True)
class ConversationGatewayState:
    runtime: ProviderRuntime
    conversation: DevConversation
    created_at: float
    last_accessed_at: float
    history: list[tuple[str, str]] = field(default_factory=list)
    pending_error: ProviderRecoverableError | None = None
    pending_message: str | None = None
    pending_agent_key: str | None = None


@dataclass(slots=True)
class TaskGatewayState:
    runtime: ProviderRuntime
    request: str
    created_at: float
    last_accessed_at: float
    status: TaskGatewayStatus = TaskGatewayStatus.PENDING
    plan: TaskPlan | None = None
    pending_error: ProviderRecoverableError | None = None
    pending_stage: str | None = None
    budget_error: OrchestrationBudgetExceeded | None = None
    blocked_reason: str | None = None
    required_disabled_agents: tuple[str, ...] = ()
    failure: dict[str, Any] | None = None


class AgentDevKitGateway:
    """Client-neutral façade over one fixed consuming project.

    The project root is bound when the gateway starts. Tool callers cannot
    provide arbitrary filesystem paths.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        registry: ProviderRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        preference_profile: PreferenceProfile | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.config: ProjectAgentDevKitConfig = load_project_config(
            self.project_root
        )
        self.registry = registry or build_default_registry()
        self.tool_registry = tool_registry
        self.preference_profile = preference_profile
        self._clock = clock or monotonic
        self._conversations: dict[str, ConversationGatewayState] = {}
        self._tasks: dict[str, TaskGatewayState] = {}

    def status(self) -> dict[str, Any]:
        """Return safe project/runtime metadata without provider secrets."""

        self.cleanup_sessions()
        provider = self.config.provider
        return {
            "status": "ok",
            "project": self.config.name,
            "project_directory": self.project_root.name,
            "enabled_agents": list(self.config.enabled_agents),
            "stack": dict(self.config.stack),
            "provider": {
                "primary": provider.provider,
                "fallback_policy": provider.fallback_policy,
                "fallbacks": [
                    item.provider for item in provider.fallbacks
                ],
            },
            "conversation_sessions": len(self._conversations),
            "task_sessions": len(self._tasks),
            "session_ttl_seconds": self.config.gateway.session_ttl_seconds,
            "max_sessions": self.config.gateway.max_sessions,
        }

    def chat(
        self,
        message: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Send one message through a persistent Agent Dev Kit conversation."""

        text = message.strip()
        if not text:
            raise ValueError("message cannot be empty.")

        self.cleanup_sessions()

        if session_id is not None:
            state_id = session_id
            state = self._conversation_state(state_id)
        else:
            self._ensure_session_capacity()
            state_id = self._new_id("chat")
            runtime = self._new_runtime()
            now = self._clock()
            state = ConversationGatewayState(
                runtime=runtime,
                conversation=runtime.kit.conversation(),
                created_at=now,
                last_accessed_at=now,
            )
            self._conversations[state_id] = state

        if state.pending_error is not None:
            return {
                "status": "fallback_pending",
                "session_id": state_id,
                "message": (
                    "A provider fallback decision is pending. "
                    "Approve or reject it before sending another message."
                ),
            }

        return self._send_chat(state_id, state, text)

    def chat_fallback(
        self,
        session_id: str,
        *,
        approve: bool,
    ) -> dict[str, Any]:
        """Approve/reject a pending chat provider fallback and resume safely."""

        state = self._conversation_state(session_id)
        if state.pending_error is None or state.pending_message is None:
            raise ValueError(
                f"Conversation '{session_id}' has no pending fallback."
            )

        if not approve:
            provider = state.runtime.current_target.provider
            state.pending_error = None
            state.pending_message = None
            state.pending_agent_key = None
            return {
                "status": "fallback_rejected",
                "session_id": session_id,
                "provider": provider,
            }

        error = state.pending_error
        message = state.pending_message
        agent_key = state.pending_agent_key

        new_kit = state.runtime.switch_after_error(
            error,
            confirm_switch=lambda current, next_target, cause: True,
        )
        state.conversation = new_kit.conversation(
            start_agent=agent_key,
        )
        state.pending_error = None
        state.pending_message = None
        state.pending_agent_key = None

        return self._send_chat(session_id, state, message)

    def reset_chat(self, session_id: str) -> dict[str, Any]:
        """Delete one gateway conversation and its transcript."""

        if session_id not in self._conversations:
            raise ValueError(f"Unknown conversation '{session_id}'.")

        del self._conversations[session_id]
        return {
            "status": "reset",
            "session_id": session_id,
        }

    def start_task(self, request: str) -> dict[str, Any]:
        """Plan and execute one multi-specialist task."""

        text = request.strip()
        if not text:
            raise ValueError("request cannot be empty.")

        self.cleanup_sessions()
        self._ensure_session_capacity()
        task_id = self._new_id("task")
        now = self._clock()
        state = TaskGatewayState(
            runtime=self._new_runtime(),
            request=text,
            created_at=now,
            last_accessed_at=now,
        )
        self._tasks[task_id] = state
        return self._advance_task(task_id, state)

    def task_fallback(
        self,
        task_id: str,
        *,
        approve: bool,
    ) -> dict[str, Any]:
        """Approve/reject a pending task fallback and resume the same DAG."""

        state = self._task_state(task_id)
        if (
            state.status != TaskGatewayStatus.FALLBACK_PENDING
            or state.pending_error is None
        ):
            raise ValueError(f"Task '{task_id}' has no pending fallback.")

        if not approve:
            provider = state.runtime.current_target.provider
            stage = state.pending_stage
            state.pending_error = None
            state.pending_stage = None
            state.status = TaskGatewayStatus.FAILED
            state.failure = {
                "reason": "fallback_rejected",
                "stage": stage,
                "provider": provider,
            }
            self._touch_task(state)
            return {
                "status": "fallback_rejected",
                "task_id": task_id,
                "stage": stage,
                "provider": provider,
                "plan": self._plan_payload(state.plan),
            }

        error = state.pending_error
        state.runtime.switch_after_error(
            error,
            confirm_switch=lambda current, next_target, cause: True,
        )
        state.pending_error = None
        state.pending_stage = None
        state.failure = None
        self._touch_task(state)
        return self._advance_task(task_id, state)

    def task_status(self, task_id: str) -> dict[str, Any]:
        state = self._task_state(task_id)
        return {
            "status": state.status.value,
            "task_id": task_id,
            "provider": state.runtime.current_target.provider,
            "request": state.request,
            "pending_stage": state.pending_stage,
            "blocked_reason": state.blocked_reason,
            "required_disabled_agents": list(
                state.required_disabled_agents
            ),
            "failure": (
                dict(state.failure)
                if state.failure is not None
                else None
            ),
            "budget": (
                state.budget_error.to_dict()
                if state.budget_error is not None
                else None
            ),
            "plan": self._plan_payload(state.plan),
        }

    def _send_chat(
        self,
        session_id: str,
        state: ConversationGatewayState,
        message: str,
    ) -> dict[str, Any]:
        prompt = self._conversation_prompt(state.history, message)

        try:
            result = state.conversation.ask_sync(prompt)
        except ProviderRecoverableError as exc:
            state.pending_error = exc
            state.last_accessed_at = self._clock()
            state.pending_message = message
            state.pending_agent_key = self._agent_key_for_name(
                state.runtime,
                state.conversation.active_agent.name,
            )
            return self._fallback_response(
                exc,
                state.runtime,
                session_id=session_id,
            )
        except ProviderError as exc:
            state.last_accessed_at = self._clock()
            return self._provider_error_response(
                exc,
                session_id=session_id,
            )

        state.history.append(("user", message))
        state.history.append(("assistant", result.output))
        state.last_accessed_at = self._clock()

        return {
            "status": "ok",
            "session_id": session_id,
            "provider": state.runtime.current_target.provider,
            "active_agent": result.active_agent.name,
            "output": result.output,
        }

    def _advance_task(
        self,
        task_id: str,
        state: TaskGatewayState,
    ) -> dict[str, Any]:
        if state.status in _TERMINAL_TASK_STATUSES:
            return self.task_status(task_id)

        if state.plan is None:
            state.status = TaskGatewayStatus.PLANNING
            self._touch_task(state)
            try:
                state.plan = state.runtime.kit.plan_task_sync(
                    state.request
                )
            except OrchestrationBudgetExceeded as exc:
                state.budget_error = exc
                state.pending_stage = exc.stage
                state.status = TaskGatewayStatus.REQUIRES_HUMAN_APPROVAL
                self._touch_task(state)
                return self._budget_response(
                    exc,
                    task_id=task_id,
                    plan=self._plan_payload(state.plan),
                )
            except ProviderRecoverableError as exc:
                state.pending_error = exc
                state.pending_stage = "planning"
                response = self._fallback_response(
                    exc,
                    state.runtime,
                    task_id=task_id,
                    stage="planning",
                )
                self._record_task_fallback_response(state, response)
                return response
            except ProviderError as exc:
                self._record_task_failure(
                    state,
                    error=exc,
                    stage="planning",
                )
                return self._provider_error_response(
                    exc,
                    task_id=task_id,
                    stage="planning",
                )

        missing = state.plan.missing_agents(
            state.runtime.kit.agents.keys()
        )
        if missing:
            state.status = TaskGatewayStatus.BLOCKED
            state.blocked_reason = "required_agents_disabled"
            state.required_disabled_agents = tuple(missing)
            state.plan.execution_status = "blocked"
            if state.plan.trace is not None:
                state.runtime.kit._persist_trace(
                    state.plan,
                    "blocked",
                )
            self._touch_task(state)
            return {
                "status": state.status.value,
                "task_id": task_id,
                "reason": state.blocked_reason,
                "required_disabled_agents": list(missing),
                "plan": self._plan_payload(state.plan),
            }

        state.status = TaskGatewayStatus.EXECUTING
        state.blocked_reason = None
        state.required_disabled_agents = ()
        self._touch_task(state)

        try:
            state.runtime.kit.execute_plan_sync(state.plan)
        except OrchestrationBudgetExceeded as exc:
            state.budget_error = exc
            state.pending_stage = exc.stage
            state.status = TaskGatewayStatus.REQUIRES_HUMAN_APPROVAL
            self._touch_task(state)
            return self._budget_response(
                exc,
                task_id=task_id,
                plan=self._plan_payload(state.plan),
            )
        except ProviderRecoverableError as exc:
            state.pending_error = exc
            state.pending_stage = "execution"
            response = self._fallback_response(
                exc,
                state.runtime,
                task_id=task_id,
                stage="execution",
                plan=self._plan_payload(state.plan),
            )
            self._record_task_fallback_response(state, response)
            return response
        except ProviderError as exc:
            self._record_task_failure(
                state,
                error=exc,
                stage="execution",
            )
            return self._provider_error_response(
                exc,
                task_id=task_id,
                stage="execution",
                plan=self._plan_payload(state.plan),
            )
        except Exception as exc:
            state.status = TaskGatewayStatus.FAILED
            state.failure = {
                "reason": "execution_error",
                "stage": "execution",
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
            self._touch_task(state)
            raise

        state.status = TaskGatewayStatus.COMPLETED
        state.pending_stage = None
        state.failure = None
        self._touch_task(state)
        return {
            "status": state.status.value,
            "task_id": task_id,
            "provider": state.runtime.current_target.provider,
            "plan": self._plan_payload(state.plan),
        }

    def _record_task_fallback_response(
        self,
        state: TaskGatewayState,
        response: dict[str, Any],
    ) -> None:
        if response.get("status") == "fallback_required":
            state.status = TaskGatewayStatus.FALLBACK_PENDING
            state.failure = None
        else:
            state.status = TaskGatewayStatus.FAILED
            state.failure = {
                "reason": "provider_error",
                "stage": state.pending_stage,
                "provider": response.get("provider"),
                "error_type": response.get("error_type"),
                "message": response.get("message"),
            }
            state.pending_error = None
        self._touch_task(state)

    def _record_task_failure(
        self,
        state: TaskGatewayState,
        *,
        error: ProviderError,
        stage: str,
    ) -> None:
        state.status = TaskGatewayStatus.FAILED
        state.pending_stage = stage
        state.failure = {
            "reason": "provider_error",
            "stage": stage,
            "provider": error.provider,
            "error_type": error.__class__.__name__,
            "message": str(error),
        }
        self._touch_task(state)

    @staticmethod
    def _budget_response(
        error: OrchestrationBudgetExceeded,
        **context: Any,
    ) -> dict[str, Any]:
        return {
            **error.to_dict(),
            **context,
        }

    def _fallback_response(
        self,
        error: ProviderRecoverableError,
        runtime: ProviderRuntime,
        **context: Any,
    ) -> dict[str, Any]:
        try:
            runtime.switch_after_error(error)
        except ProviderFallbackRequired as required:
            return {
                "status": "fallback_required",
                **context,
                "current_provider": required.current_provider,
                "next_provider": required.next_provider,
                "error_type": error.__class__.__name__,
                "message": str(error),
            }
        except ProviderRecoverableError:
            return {
                "status": "provider_error",
                **context,
                "provider": runtime.current_target.provider,
                "error_type": error.__class__.__name__,
                "message": str(error),
                "fallback_available": False,
            }

        raise RuntimeError(
            "Provider fallback unexpectedly switched without approval."
        )

    @staticmethod
    def _provider_error_response(
        error: ProviderError,
        **context: Any,
    ) -> dict[str, Any]:
        return {
            "status": "provider_error",
            **context,
            "provider": error.provider,
            "error_type": error.__class__.__name__,
            "message": str(error),
        }

    def _new_runtime(self) -> ProviderRuntime:
        return ProviderRuntime(
            registry=self.registry,
            project_config=self.config,
            tool_registry=self.tool_registry,
            preference_profile=self.preference_profile,
        )

    def _conversation_state(
        self,
        session_id: str,
    ) -> ConversationGatewayState:
        self.cleanup_sessions()
        try:
            state = self._conversations[session_id]
        except KeyError as exc:
            raise ValueError(
                f"Unknown or expired conversation '{session_id}'."
            ) from exc
        state.last_accessed_at = self._clock()
        return state

    def _task_state(self, task_id: str) -> TaskGatewayState:
        self.cleanup_sessions()
        try:
            state = self._tasks[task_id]
        except KeyError as exc:
            raise ValueError(
                f"Unknown or expired task '{task_id}'."
            ) from exc
        self._touch_task(state)
        return state

    def cleanup_sessions(self) -> dict[str, int]:
        """Remove in-memory sessions whose inactivity exceeded the TTL."""

        now = self._clock()
        ttl = self.config.gateway.session_ttl_seconds

        expired_conversations = [
            key
            for key, state in self._conversations.items()
            if now - state.last_accessed_at >= ttl
        ]
        expired_tasks = [
            key
            for key, state in self._tasks.items()
            if now - state.last_accessed_at >= ttl
        ]

        for key in expired_conversations:
            del self._conversations[key]
        for key in expired_tasks:
            del self._tasks[key]

        return {
            "conversations": len(expired_conversations),
            "tasks": len(expired_tasks),
        }

    def _ensure_session_capacity(self) -> None:
        self.cleanup_sessions()
        current = len(self._conversations) + len(self._tasks)
        limit = self.config.gateway.max_sessions
        if current >= limit:
            raise RuntimeError(
                "Gateway session limit reached. Reset a conversation, wait "
                "for TTL cleanup, or increase gateway.max_sessions."
            )

    def _touch_task(self, state: TaskGatewayState) -> None:
        state.last_accessed_at = self._clock()

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    @staticmethod
    def _conversation_prompt(
        history: list[tuple[str, str]],
        message: str,
    ) -> str:
        if not history:
            return message

        transcript = "\n".join(
            f"{role}: {content}"
            for role, content in history
        )
        return (
            "Continue the same conversation using this client-neutral "
            "transcript as context.\n\n"
            f"{transcript}\n"
            f"user: {message}\n"
            "Respond to the latest user message."
        )

    @staticmethod
    def _agent_key_for_name(
        runtime: ProviderRuntime,
        name: str,
    ) -> str:
        for key, handle in runtime.kit.agents.items():
            if handle.name == name:
                return key
        raise ValueError(f"Active agent '{name}' is not enabled.")

    @staticmethod
    def _plan_payload(plan: TaskPlan | None) -> dict[str, Any] | None:
        if plan is None:
            return None

        profile = plan.profile
        trace = plan.trace

        return {
            "request": plan.request,
            "profile": (
                {
                    "summary": profile.summary,
                    "classification": profile.classification,
                    "risk_flags": list(profile.risk_flags),
                    "durable_artifacts": list(profile.durable_artifacts),
                }
                if profile is not None
                else None
            ),
            "agent_decisions": [
                {
                    "agent": item.agent,
                    "selected": item.selected,
                    "gate": item.gate,
                    "reason": item.reason,
                }
                for item in plan.agent_decisions
            ],
            "required_disabled_agents": list(
                plan.required_disabled_agents
            ),
            "notes": plan.notes,
            "is_complete": plan.is_complete,
            "execution_status": plan.execution_status,
            "provider_calls": plan.provider_calls,
            "calls_avoided_by_reuse": plan.calls_avoided_by_reuse,
            "orchestration_trace": (
                {
                    "request_fingerprint": trace.request_fingerprint,
                    "classification": trace.classification,
                    "model_calls": trace.model_calls,
                    "provider_calls": trace.provider_calls,
                    "calls_avoided_by_reuse": trace.calls_avoided_by_reuse,
                    "deduplicated_context_items": trace.deduplicated_context_items,
                    "context_chars_total": trace.context_chars_total,
                    "max_context_chars_observed": trace.max_context_chars_observed,
                    "context_truncations": trace.context_truncations,
                    "budget_events": list(trace.budget_events),
                    "handoffs": trace.handoffs,
                    "revisits": trace.revisits,
                    "status": trace.status,
                    "node_durations_ms": dict(trace.node_durations_ms),
                }
                if trace is not None
                else None
            ),
            "nodes": [
                {
                    "id": node.id,
                    "agent": node.agent,
                    "phase": node.phase,
                    "objective": node.objective,
                    "depends_on": list(node.depends_on),
                    "status": node.status,
                    "output": node.output,
                    "evidence": dict(node.evidence),
                }
                for node in plan.nodes
            ],
        }
