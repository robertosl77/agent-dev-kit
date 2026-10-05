import json
from pathlib import Path

from agent_dev_kit.gateway import AgentDevKitGateway
from agent_dev_kit.provider_errors import (
    ProviderExecutionError,
    ProviderQuotaExceeded,
)
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class GatewayProvider(AgentProvider):
    def __init__(
        self,
        key: str,
        *,
        fail_chat_once: bool = False,
        fail_backend_once: bool = False,
        fail_backend_fatal: bool = False,
        required_disabled_agents: tuple[str, ...] = (),
    ) -> None:
        self.key = key
        self.fail_chat_once = fail_chat_once
        self.fail_backend_once = fail_backend_once
        self.fail_backend_fatal = fail_backend_fatal
        self.required_disabled_agents = required_disabled_agents
        self.chat_failed = False
        self.backend_failed = False

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native=definition,
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        if (
            agent.name == "Agent Triage Planner"
            and "Planning-only operation" in message
        ):
            payload = {
                "request": "Fix report",
                "profile": {
                    "summary": "Fix report service behavior.",
                    "classification": "backend_bug",
                    "risk_flags": ["backend_change", "behavior_regression"],
                    "durable_artifacts": ["project_docs"],
                },
                "agent_decisions": [
                    {
                        "agent": "backend",
                        "selected": True,
                        "gate": "backend_change",
                        "reason": "Server behavior changes.",
                    },
                    {
                        "agent": "testing",
                        "selected": True,
                        "gate": "behavior_regression",
                        "reason": "Regression validation is required.",
                    },
                    {
                        "agent": "documentation",
                        "selected": True,
                        "gate": "durable_artifact",
                        "reason": "Project documentation must be synchronized.",
                    },
                ],
                "required_disabled_agents": list(
                    self.required_disabled_agents
                ),
                "notes": None,
                "nodes": [
                    {
                        "id": "backend",
                        "agent": "backend",
                        "phase": "implementation",
                        "objective": "Fix the service.",
                        "depends_on": [],
                    },
                    {
                        "id": "testing",
                        "agent": "testing",
                        "phase": "validation",
                        "objective": "Validate the service.",
                        "depends_on": ["backend"],
                    },
                    {
                        "id": "documentation",
                        "agent": "documentation",
                        "phase": "documentation",
                        "objective": "Document the evidence.",
                        "depends_on": ["testing"],
                    },
                ],
            }
            return ProviderRunResult(
                output=json.dumps(payload),
                active_agent=agent,
            )

        if (
            self.fail_chat_once
            and agent.name == "Agent Triage"
            and not self.chat_failed
        ):
            self.chat_failed = True
            raise ProviderQuotaExceeded(
                "chat quota exhausted",
                provider=self.key,
            )

        if self.fail_backend_fatal and agent.name == "Agent Backend":
            raise ProviderExecutionError(
                "fatal backend failure",
                provider=self.key,
            )

        if (
            self.fail_backend_once
            and agent.name == "Agent Backend"
            and not self.backend_failed
        ):
            self.backend_failed = True
            raise ProviderQuotaExceeded(
                "backend quota exhausted",
                provider=self.key,
            )

        return ProviderRunResult(
            output=f"{self.key}:{agent.name}:{message}",
            active_agent=agent,
        )


def project_config(tmp_path: Path) -> None:
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: GatewayExample

stack:
  backend:
    language: Python
    framework: FastAPI

provider:
  name: primary
  fallback_policy: ask
  fallbacks:
    - name: backup

agents:
  enabled:
    - triage
    - backend
    - testing
    - documentation
""",
    )


def make_registry(
    *,
    primary_chat_failure: bool = False,
    primary_backend_failure: bool = False,
    primary_backend_fatal: bool = False,
    required_disabled_agents: tuple[str, ...] = (),
):
    registry = ProviderRegistry()
    registry.register(
        "primary",
        lambda config: GatewayProvider(
            "primary",
            fail_chat_once=primary_chat_failure,
            fail_backend_once=primary_backend_failure,
            fail_backend_fatal=primary_backend_fatal,
            required_disabled_agents=required_disabled_agents,
        ),
    )
    registry.register(
        "backup",
        lambda config: GatewayProvider(
            "backup",
            required_disabled_agents=required_disabled_agents,
        ),
    )
    return registry


def test_gateway_status_does_not_expose_absolute_project_path(tmp_path):
    project_config(tmp_path)
    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(),
    )

    status = gateway.status()

    assert status["project"] == "GatewayExample"
    assert status["project_directory"] == tmp_path.name
    assert "project_root" not in status
    assert status["enabled_agents"] == [
        "triage",
        "backend",
        "testing",
        "documentation",
    ]


def test_gateway_chat_persists_session(tmp_path):
    project_config(tmp_path)
    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(),
    )

    first = gateway.chat("hello")
    second = gateway.chat(
        "continue",
        session_id=first["session_id"],
    )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert first["session_id"] == second["session_id"]
    assert "user: hello" in second["output"]


def test_chat_fallback_requires_separate_approval(tmp_path):
    project_config(tmp_path)
    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(primary_chat_failure=True),
    )

    first = gateway.chat("hello")

    assert first["status"] == "fallback_required"
    assert first["current_provider"] == "primary"
    assert first["next_provider"] == "backup"

    resumed = gateway.chat_fallback(
        first["session_id"],
        approve=True,
    )

    assert resumed["status"] == "ok"
    assert resumed["provider"] == "backup"


def test_task_resumes_same_dag_after_approved_fallback(tmp_path):
    project_config(tmp_path)
    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(primary_backend_failure=True),
    )

    first = gateway.start_task("Fix report")

    assert first["status"] == "fallback_required"
    assert first["stage"] == "execution"
    assert first["plan"]["nodes"][0]["status"] == "pending"

    resumed = gateway.task_fallback(
        first["task_id"],
        approve=True,
    )

    assert resumed["status"] == "completed"
    assert resumed["provider"] == "backup"
    assert resumed["plan"]["orchestration_trace"]["model_calls"] >= 4
    assert resumed["plan"]["orchestration_trace"]["revisits"] == 1
    assert all(
        node["status"] == "completed"
        for node in resumed["plan"]["nodes"]
    )


def test_gateway_surfaces_budget_exceeded_as_human_approval(tmp_path):
    project_config(tmp_path)
    project_path = tmp_path / ".agent-dev-kit" / "project.yaml"
    content = project_path.read_text(encoding="utf-8")
    content = content.replace(
        "agents:\n",
        "orchestration:\n"
        "  budgets:\n"
        "    max_provider_calls: 1\n"
        "\n"
        "agents:\n",
    )
    project_path.write_text(content, encoding="utf-8")

    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(),
    )

    result = gateway.start_task("Fix report")

    assert result["status"] == "requires_human_approval"
    assert result["reason"] == "budget_exceeded"
    assert result["budget"] == "max_provider_calls"
    assert result["stage"] == "execution"
    assert result["plan"]["execution_status"] == "requires_human_approval"



class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def configure_gateway_lifecycle(
    tmp_path: Path,
    *,
    ttl: int = 3600,
    max_sessions: int = 100,
) -> None:
    project_path = tmp_path / ".agent-dev-kit" / "project.yaml"
    content = project_path.read_text(encoding="utf-8")
    content = content.replace(
        "agents:\n",
        "gateway:\n"
        f"  session_ttl_seconds: {ttl}\n"
        f"  max_sessions: {max_sessions}\n"
        "\n"
        "agents:\n",
    )
    project_path.write_text(content, encoding="utf-8")


def test_blocked_task_state_remains_blocked_on_status(tmp_path):
    project_config(tmp_path)
    project_path = tmp_path / ".agent-dev-kit" / "project.yaml"
    content = project_path.read_text(encoding="utf-8")
    content = content.replace("    - documentation\n", "")
    project_path.write_text(content, encoding="utf-8")

    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(
            required_disabled_agents=("documentation",),
        ),
    )

    first = gateway.start_task("Fix report")
    later = gateway.task_status(first["task_id"])

    assert first["status"] == "blocked"
    assert first["reason"] == "required_agents_disabled"
    assert later["status"] == "blocked"
    assert later["blocked_reason"] == "required_agents_disabled"
    assert later["required_disabled_agents"] == ["documentation"]


def test_fatal_provider_error_remains_failed_on_status(tmp_path):
    project_config(tmp_path)
    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(primary_backend_fatal=True),
    )

    first = gateway.start_task("Fix report")
    later = gateway.task_status(first["task_id"])

    assert first["status"] == "provider_error"
    assert later["status"] == "failed"
    assert later["failure"]["reason"] == "provider_error"
    assert later["failure"]["stage"] == "execution"
    assert later["failure"]["error_type"] == "ProviderExecutionError"


def test_fallback_pending_and_rejection_have_coherent_persisted_state(tmp_path):
    project_config(tmp_path)
    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(primary_backend_failure=True),
    )

    first = gateway.start_task("Fix report")
    pending = gateway.task_status(first["task_id"])

    assert first["status"] == "fallback_required"
    assert pending["status"] == "fallback_pending"

    rejected = gateway.task_fallback(first["task_id"], approve=False)
    failed = gateway.task_status(first["task_id"])

    assert rejected["status"] == "fallback_rejected"
    assert failed["status"] == "failed"
    assert failed["failure"]["reason"] == "fallback_rejected"


def test_budget_state_remains_requires_human_approval(tmp_path):
    project_config(tmp_path)
    project_path = tmp_path / ".agent-dev-kit" / "project.yaml"
    content = project_path.read_text(encoding="utf-8")
    content = content.replace(
        "agents:\n",
        "orchestration:\n"
        "  budgets:\n"
        "    max_provider_calls: 1\n"
        "\n"
        "agents:\n",
    )
    project_path.write_text(content, encoding="utf-8")

    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(),
    )

    first = gateway.start_task("Fix report")
    later = gateway.task_status(first["task_id"])

    assert first["status"] == "requires_human_approval"
    assert later["status"] == "requires_human_approval"
    assert later["budget"]["budget"] == "max_provider_calls"


def test_gateway_ttl_cleanup_expires_idle_sessions(tmp_path):
    project_config(tmp_path)
    configure_gateway_lifecycle(tmp_path, ttl=10)
    clock = FakeClock()
    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(),
        clock=clock,
    )

    chat = gateway.chat("hello")
    clock.advance(11)

    cleaned = gateway.cleanup_sessions()

    assert cleaned == {"conversations": 1, "tasks": 0}
    assert gateway.status()["conversation_sessions"] == 0

    try:
        gateway.chat("continue", session_id=chat["session_id"])
    except ValueError as exc:
        assert "expired conversation" in str(exc)
    else:
        raise AssertionError("Expected expired conversation to be rejected")


def test_gateway_session_limit_is_enforced_after_cleanup(tmp_path):
    project_config(tmp_path)
    configure_gateway_lifecycle(tmp_path, ttl=10, max_sessions=1)
    clock = FakeClock()
    gateway = AgentDevKitGateway(
        tmp_path,
        registry=make_registry(),
        clock=clock,
    )

    gateway.chat("hello")

    try:
        gateway.chat("second")
    except RuntimeError as exc:
        assert "session limit" in str(exc)
    else:
        raise AssertionError("Expected session limit failure")

    clock.advance(11)
    second = gateway.chat("after cleanup")

    assert second["status"] == "ok"
