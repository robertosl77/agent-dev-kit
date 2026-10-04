from pathlib import Path

import pytest

from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.project_config import load_project_config
from agent_dev_kit.provider_errors import ProviderQuotaExceeded
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)
from agent_dev_kit.task_plan import DisabledAgentRequiredError


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class SmokeProvider(AgentProvider):
    def __init__(self, key: str, *, fail_backend_once: bool = False):
        self.key = key
        self.fail_backend_once = fail_backend_once
        self.backend_failed = False
        self.definitions = {}
        self.handoffs = {}

    def create_agent(self, definition, *, handoffs=(), tools=()):
        self.definitions[definition.name] = definition
        handle = AgentHandle(
            provider=self.key,
            name=definition.name,
            native=definition,
        )
        self.handoffs[definition.name] = tuple(
            item.name for item in handoffs
        )
        return handle

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)
        self.handoffs[agent.name] = tuple(
            item.name for item in handoffs
        )

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        if agent.name == "Agent Triage" and "Planning-only operation" in message:
            enabled_block = message.split(
                "Enabled agent keys:\n",
                1,
            )[1].split(
                "\n\nKnown but disabled agent keys:",
                1,
            )[0]

            if "ux_ui" not in enabled_block:
                return ProviderRunResult(
                    output="""{
                      "request": "Fix progress report",
                      "profile": {
                        "summary": "Redesign progress report experience.",
                        "classification": "ux_change",
                        "risk_flags": ["ux_change"],
                        "durable_artifacts": []
                      },
                      "agent_decisions": [
                        {"agent": "architecture", "selected": false, "gate": "cross_layer", "reason": "No architecture decision before UX definition."},
                        {"agent": "backend", "selected": false, "gate": "backend_change", "reason": "No backend work can be planned yet."},
                        {"agent": "frontend", "selected": false, "gate": "frontend_change", "reason": "Frontend implementation waits for UX."},
                        {"agent": "testing", "selected": false, "gate": "behavior_regression", "reason": "Validation waits for implementation."},
                        {"agent": "reviewer", "selected": false, "gate": "technical_review", "reason": "Review waits for implementation."},
                        {"agent": "documentation", "selected": false, "gate": "durable_artifact", "reason": "No durable artifact requested."}
                      ],
                      "required_disabled_agents": ["ux_ui"],
                      "nodes": []
                    }""",
                    active_agent=agent,
                )

            return ProviderRunResult(
                output="""{
                  "request": "Fix progress report data and UX",
                  "profile": {
                    "summary": "Fix progress report data and UX.",
                    "classification": "cross_layer_feature_fix",
                    "risk_flags": [
                      "cross_layer",
                      "persistence_change",
                      "ux_change",
                      "backend_change",
                      "frontend_change",
                      "behavior_regression",
                      "technical_review"
                    ],
                    "durable_artifacts": ["technical_spec"]
                  },
                  "agent_decisions": [
                    {"agent": "architecture", "selected": true, "gate": "cross_layer", "reason": "Cross-layer contracts must be defined."},
                    {"agent": "database", "selected": true, "gate": "persistence_change", "reason": "Progress data persistence is affected."},
                    {"agent": "ux_ui", "selected": true, "gate": "ux_change", "reason": "Report experience changes."},
                    {"agent": "backend", "selected": true, "gate": "backend_change", "reason": "Progress API behavior changes."},
                    {"agent": "frontend", "selected": true, "gate": "frontend_change", "reason": "Report screen changes."},
                    {"agent": "testing", "selected": true, "gate": "behavior_regression", "reason": "Changed behavior needs regression validation."},
                    {"agent": "reviewer", "selected": true, "gate": "technical_review", "reason": "Cross-layer change needs independent review."},
                    {"agent": "documentation", "selected": true, "gate": "durable_artifact", "reason": "Technical specification must stay synchronized."}
                  ],
                  "required_disabled_agents": [],
                  "nodes": [
                    {"id": "architecture", "agent": "architecture", "phase": "design", "objective": "Define boundaries and contracts.", "depends_on": []},
                    {"id": "database", "agent": "database", "phase": "implementation", "objective": "Validate progress data model.", "depends_on": ["architecture"]},
                    {"id": "ux", "agent": "ux_ui", "phase": "design", "objective": "Define improved report experience.", "depends_on": ["architecture"]},
                    {"id": "backend", "agent": "backend", "phase": "implementation", "objective": "Implement correct progress API.", "depends_on": ["database"]},
                    {"id": "frontend", "agent": "frontend", "phase": "implementation", "objective": "Implement the report screen.", "depends_on": ["ux", "backend"]},
                    {"id": "testing", "agent": "testing", "phase": "validation", "objective": "Automate technical validation.", "depends_on": ["backend", "frontend"]},
                    {"id": "reviewer", "agent": "reviewer", "phase": "validation", "objective": "Review the complete delivery.", "depends_on": ["testing"]},
                    {"id": "documentation", "agent": "documentation", "phase": "documentation", "objective": "Synchronize durable technical decisions.", "depends_on": ["reviewer"]}
                  ]
                }""",
                active_agent=agent,
            )

        if (
            self.fail_backend_once
            and agent.name == "Agent Backend"
            and not self.backend_failed
        ):
            self.backend_failed = True
            raise ProviderQuotaExceeded(
                "primary provider quota exhausted",
                provider=self.key,
            )

        return ProviderRunResult(
            output=f"{self.key} completed {agent.name}",
            active_agent=agent,
        )


def project_yaml(enabled_agents: list[str]) -> str:
    enabled = "\n".join(
        f"    - {agent}" for agent in enabled_agents
    )
    return f"""
project:
  name: LibreriaInglesSmoke

stack:
  backend:
    language: Python
    framework: FastAPI
  frontend:
    framework: Angular
  ui:
    framework: Bootstrap
  database:
    engine: SQLite

provider:
  name: primary
  fallback_policy: ask
  fallbacks:
    - name: backup

agents:
  enabled:
{enabled}
"""


def build_runtime(tmp_path, enabled_agents):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        project_yaml(enabled_agents),
    )
    write(
        tmp_path / ".agent-dev-kit" / "preferences.yaml",
        """
preferences:
  - id: task_traceability
    rule: "Keep durable task evidence traceable."
    agents:
      - documentation
""",
    )

    config = load_project_config(tmp_path)

    providers = {}
    registry = ProviderRegistry()

    def primary_factory(config):
        provider = SmokeProvider(
            "primary",
            fail_backend_once=True,
        )
        providers["primary"] = provider
        return provider

    def backup_factory(config):
        provider = SmokeProvider("backup")
        providers["backup"] = provider
        return provider

    registry.register("primary", primary_factory)
    registry.register("backup", backup_factory)

    return (
        config,
        ProviderRuntime(
            registry=registry,
            project_config=config,
        ),
        providers,
    )


def test_end_to_end_consumer_flow_with_dag_preferences_and_fallback(tmp_path):
    enabled = [
        "triage",
        "architecture",
        "database",
        "ux_ui",
        "backend",
        "frontend",
        "testing",
        "reviewer",
        "documentation",
    ]
    config, runtime, providers = build_runtime(tmp_path, enabled)

    assert config.stack["backend"]["framework"] == "FastAPI"
    assert config.stack["frontend"]["framework"] == "Angular"
    assert config.stack["database"]["engine"] == "SQLite"

    primary_kit = runtime.kit
    primary = providers["primary"]

    assert "modular_structure" in (
        primary.definitions["Agent Backend"].instructions
    )
    assert "task_traceability" in (
        primary.definitions["Agent Documentation"].instructions
    )
    assert "Agent Database" in primary.handoffs["Agent Architecture"]
    assert "Agent Backend" in primary.handoffs["Agent Architecture"]

    plan = runtime.run_with_fallback_sync(
        lambda kit: kit.plan_task_sync(
            "The progress report has incorrect data and poor UX."
        ),
        confirm_switch=lambda current, next_target, error: True,
    )

    result = runtime.run_with_fallback_sync(
        lambda kit: kit.execute_plan_sync(plan),
        confirm_switch=lambda current, next_target, error: True,
    )

    assert result.is_complete
    assert runtime.current_target.provider == "backup"

    assert result.node("architecture").evidence["provider"] == "primary"
    assert result.node("database").evidence["provider"] == "primary"
    assert result.node("ux").evidence["provider"] == "primary"
    assert result.node("backend").evidence["provider"] == "backup"
    assert result.node("frontend").evidence["provider"] == "backup"
    assert result.node("testing").status == "completed"
    assert result.node("reviewer").status == "completed"
    assert result.node("documentation").status == "completed"


def test_end_to_end_blocks_required_disabled_specialist(tmp_path):
    enabled = [
        "triage",
        "architecture",
        "backend",
        "frontend",
        "testing",
        "reviewer",
        "documentation",
    ]
    _, runtime, _ = build_runtime(tmp_path, enabled)

    plan = runtime.kit.plan_task_sync(
        "Redesign the progress report."
    )

    with pytest.raises(DisabledAgentRequiredError) as exc:
        runtime.kit.execute_plan_sync(plan)

    assert exc.value.agents == ("ux_ui",)
