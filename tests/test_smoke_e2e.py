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
                      "policy_version": 1,
                      "request": "Redesign progress report",
                      "request_summary": "Redesign the progress report experience.",
                      "request_class": "feature",
                      "issue_reference": "T-SMOKE-UX",
                      "gates": ["ux_change"],
                      "forced_agents": [],
                      "required_disabled_agents": ["ux_ui"],
                      "decisions": [
                        {
                          "agent": "ux_ui",
                          "selected": true,
                          "reason": "The requested work is UX design."
                        },
                        {
                          "agent": "frontend",
                          "selected": false,
                          "reason": "This request only asks for the design."
                        }
                      ],
                      "artifacts": [],
                      "nodes": []
                    }""",
                    active_agent=agent,
                )

            return ProviderRunResult(
                output="""{
                  "policy_version": 1,
                  "request": "Fix progress report data and UX and update technical spec",
                  "request_summary": "Fix incorrect progress data, improve the report UX, and update the technical specification.",
                  "request_class": "bug",
                  "issue_reference": "T-SMOKE-001",
                  "gates": [
                    "architecture_change",
                    "database_change",
                    "ux_change",
                    "backend_change",
                    "frontend_change",
                    "testing_required",
                    "review_required",
                    "durable_documentation"
                  ],
                  "forced_agents": [],
                  "required_disabled_agents": [],
                  "decisions": [
                    {"agent": "architecture", "selected": true, "reason": "Data and UI contracts cross layers."},
                    {"agent": "database", "selected": true, "reason": "Progress persistence/model must be validated."},
                    {"agent": "ux_ui", "selected": true, "reason": "The report experience changes."},
                    {"agent": "backend", "selected": true, "reason": "Progress API behavior changes."},
                    {"agent": "frontend", "selected": true, "reason": "The report screen changes."},
                    {"agent": "testing", "selected": true, "reason": "Bug requires regression coverage."},
                    {"agent": "reviewer", "selected": true, "reason": "Cross-layer change warrants independent technical review."},
                    {"agent": "documentation", "selected": true, "reason": "Technical specification update was requested."},
                    {"agent": "security", "selected": false, "reason": "No new security or trust surface is introduced."}
                  ],
                  "artifacts": [
                    {"kind": "technical_spec", "action": "update"}
                  ],
                  "nodes": [
                    {
                      "id": "architecture",
                      "agent": "architecture",
                      "objective": "Define the affected boundaries and contracts.",
                      "phase": "design",
                      "depends_on": []
                    },
                    {
                      "id": "database",
                      "agent": "database",
                      "objective": "Validate the progress data model.",
                      "phase": "analysis",
                      "depends_on": ["architecture"]
                    },
                    {
                      "id": "ux",
                      "agent": "ux_ui",
                      "objective": "Define the improved report experience.",
                      "phase": "design",
                      "depends_on": ["architecture"]
                    },
                    {
                      "id": "backend",
                      "agent": "backend",
                      "objective": "Implement the corrected progress API.",
                      "phase": "implementation",
                      "depends_on": ["database"]
                    },
                    {
                      "id": "frontend",
                      "agent": "frontend",
                      "objective": "Implement the improved report screen.",
                      "phase": "implementation",
                      "depends_on": ["ux", "backend"]
                    },
                    {
                      "id": "testing",
                      "agent": "testing",
                      "objective": "Automate regression validation.",
                      "phase": "verification",
                      "depends_on": ["backend", "frontend"]
                    },
                    {
                      "id": "reviewer",
                      "agent": "reviewer",
                      "objective": "Review the complete cross-layer delivery.",
                      "phase": "verification",
                      "depends_on": ["testing"]
                    },
                    {
                      "id": "documentation",
                      "agent": "documentation",
                      "objective": "Update the technical specification with durable decisions.",
                      "phase": "documentation",
                      "depends_on": ["reviewer"]
                    }
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

documentation:
  templates:
    technical_spec: docs/templates/technical-spec.md

orchestration:
  trace:
    path: .agent-dev-kit/runtime/orchestration.jsonl
    retain_request_text: false

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

    write(
        tmp_path / "docs" / "templates" / "technical-spec.md",
        "# Technical specification template\n",
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
            "The progress report has incorrect data and poor UX. "
            "Update the technical specification too."
        ),
        confirm_switch=lambda current, next_target, error: True,
    )

    result = runtime.run_with_fallback_sync(
        lambda kit: kit.execute_plan_sync(plan),
        confirm_switch=lambda current, next_target, error: True,
    )

    assert result.is_complete
    assert runtime.current_target.provider == "backup"
    assert result.policy_version == 1
    assert result.trace is not None
    assert result.trace.raw_request is None
    assert result.trace.provider_calls == 10
    assert result.trace.revisits == 1
    assert "security" not in [node.agent for node in result.nodes]
    assert (
        result.trace.request_summary
        == "Fix incorrect progress data, improve the report UX, and update the technical specification."
    )
    trace_file = (
        tmp_path
        / ".agent-dev-kit"
        / "runtime"
        / "orchestration.jsonl"
    )
    assert trace_file.is_file()

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
