from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
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


@dataclass(slots=True)
class ConversationGatewayState:
    runtime: ProviderRuntime
    conversation: DevConversation
    history: list[tuple[str, str]] = field(default_factory=list)
    pending_error: ProviderRecoverableError | None = None
    pending_message: str | None = None
    pending_agent_key: str | None = None


@dataclass(slots=True)
class TaskGatewayState:
    runtime: ProviderRuntime
    request: str
    plan: TaskPlan | None = None
    pending_error: ProviderRecoverableError | None = None
    pending_stage: str | None = None
    budget_error: OrchestrationBudgetExceeded | None = None
    completed: bool = False


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
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.config: ProjectAgentDevKitConfig = load_project_config(
            self.project_root
        )
        self.registry = registry or build_default_registry()
        self.tool_registry = tool_registry
        self.preference_profile = preference_profile
        self._conversations: dict[str, ConversationGatewayState] = {}
        self._tasks: dict[str, TaskGatewayState] = {}

    def status(self) -> dict[str, Any]:
        """Return safe project/runtime metadata without provider secrets."""

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

        state_id = session_id or self._new_id("chat")
        state = self._conversations.get(state_id)

        if state is None:
            runtime = self._new_runtime()
            state = ConversationGatewayState(
                runtime=runtime,
                conversation=runtime.kit.conversation(),
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

        task_id = self._new_id("task")
        state = TaskGatewayState(
            runtime=self._new_runtime(),
            request=text,
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
        if state.pending_error is None:
            raise ValueError(f"Task '{task_id}' has no pending fallback.")

        if not approve:
            provider = state.runtime.current_target.provider
            state.pending_error = None
            stage = state.pending_stage
            state.pending_stage = None
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
        return self._advance_task(task_id, state)

    def task_status(self, task_id: str) -> dict[str, Any]:
        state = self._task_state(task_id)
        return {
            "status": (
                "completed"
                if state.completed
                else (
                    "requires_human_approval"
                    if state.budget_error is not None
                    else (
                        "fallback_pending"
                        if state.pending_error is not None
                        else "in_progress"
                    )
                )
            ),
            "task_id": task_id,
            "provider": state.runtime.current_target.provider,
            "request": state.request,
            "pending_stage": state.pending_stage,
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
            return self._provider_error_response(
                exc,
                session_id=session_id,
            )

        state.history.append(("user", message))
        state.history.append(("assistant", result.output))

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
        if state.completed or state.budget_error is not None:
            return self.task_status(task_id)

        if state.plan is None:
            try:
                state.plan = state.runtime.kit.plan_task_sync(
                    state.request
                )
            except OrchestrationBudgetExceeded as exc:
                state.budget_error = exc
                state.pending_stage = exc.stage
                return self._budget_response(
                    exc,
                    task_id=task_id,
                    plan=self._plan_payload(state.plan),
                )
            except ProviderRecoverableError as exc:
                state.pending_error = exc
                state.pending_stage = "planning"
                return self._fallback_response(
                    exc,
                    state.runtime,
                    task_id=task_id,
                    stage="planning",
                )
            except ProviderError as exc:
                return self._provider_error_response(
                    exc,
                    task_id=task_id,
                    stage="planning",
                )

        missing = state.plan.missing_agents(
            state.runtime.kit.agents.keys()
        )
        if missing:
            return {
                "status": "blocked",
                "task_id": task_id,
                "reason": "required_agents_disabled",
                "required_disabled_agents": list(missing),
                "plan": self._plan_payload(state.plan),
            }

        try:
            state.runtime.kit.execute_plan_sync(state.plan)
        except OrchestrationBudgetExceeded as exc:
            state.budget_error = exc
            state.pending_stage = exc.stage
            return self._budget_response(
                exc,
                task_id=task_id,
                plan=self._plan_payload(state.plan),
            )
        except ProviderRecoverableError as exc:
            state.pending_error = exc
            state.pending_stage = "execution"
            return self._fallback_response(
                exc,
                state.runtime,
                task_id=task_id,
                stage="execution",
                plan=self._plan_payload(state.plan),
            )
        except ProviderError as exc:
            return self._provider_error_response(
                exc,
                task_id=task_id,
                stage="execution",
                plan=self._plan_payload(state.plan),
            )

        state.completed = True
        return {
            "status": "completed",
            "task_id": task_id,
            "provider": state.runtime.current_target.provider,
            "plan": self._plan_payload(state.plan),
        }

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
        try:
            return self._conversations[session_id]
        except KeyError as exc:
            raise ValueError(
                f"Unknown conversation '{session_id}'."
            ) from exc

    def _task_state(self, task_id: str) -> TaskGatewayState:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise ValueError(f"Unknown task '{task_id}'.") from exc

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
