from pathlib import Path

from agent_dev_kit.gateway import AgentDevKitGateway
from agent_dev_kit.provider_errors import ProviderQuotaExceeded
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
    ) -> None:
        self.key = key
        self.fail_chat_once = fail_chat_once
        self.fail_backend_once = fail_backend_once
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
            return ProviderRunResult(
                output="""{
                  "request": "Fix report",
                  "profile": {
                    "summary": "Fix report service behavior.",
                    "classification": "backend_bug",
                    "risk_flags": ["backend_change", "behavior_regression"],
                    "durable_artifacts": ["project_docs"]
                  },
                  "agent_decisions": [
                    {
                      "agent": "backend",
                      "selected": true,
                      "gate": "backend_change",
                      "reason": "Server behavior changes."
                    },
                    {
                      "agent": "testing",
                      "selected": true,
                      "gate": "behavior_regression",
                      "reason": "Regression validation is required."
                    },
                    {
                      "agent": "documentation",
                      "selected": true,
                      "gate": "durable_artifact",
                      "reason": "Project documentation must be synchronized."
                    }
                  ],
                  "required_disabled_agents": [],
                  "notes": null,
                  "nodes": [
                    {
                      "id": "backend",
                      "agent": "backend",
                      "phase": "implementation",
                      "objective": "Fix the service.",
                      "depends_on": []
                    },
                    {
                      "id": "testing",
                      "agent": "testing",
                      "phase": "validation",
                      "objective": "Validate the service.",
                      "depends_on": ["backend"]
                    },
                    {
                      "id": "documentation",
                      "agent": "documentation",
                      "phase": "documentation",
                      "objective": "Document the evidence.",
                      "depends_on": ["testing"]
                    }
                  ]
                }""",
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
):
    registry = ProviderRegistry()
    registry.register(
        "primary",
        lambda config: GatewayProvider(
            "primary",
            fail_chat_once=primary_chat_failure,
            fail_backend_once=primary_backend_failure,
        ),
    )
    registry.register(
        "backup",
        lambda config: GatewayProvider("backup"),
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
