from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)
from agent_dev_kit.runtime import DevAgentKit
from agent_dev_kit.task_plan import DisabledAgentRequiredError, TaskPlan


class PlanningProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.handles = {}
        self.calls = []

    def create_agent(self, definition, *, handoffs=(), tools=()):
        handle = AgentHandle(
            provider=self.key,
            name=definition.name,
            native={"name": definition.name},
        )
        self.handles[definition.name] = handle
        return handle

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        self.calls.append((agent.name, message))

        if agent.name == "Agent Triage Planner" and "Planning-only operation" in message:
            return ProviderRunResult(
                output="""{
                  "request": "Fix report",
                  "profile": {
                    "summary": "Fix report architecture and backend behavior.",
                    "classification": "cross_layer_bug",
                    "risk_flags": ["cross_layer", "backend_change", "behavior_regression"],
                    "durable_artifacts": ["technical_spec"]
                  },
                  "agent_decisions": [
                    {"agent": "architecture", "selected": true, "gate": "cross_layer", "reason": "Boundaries must be reviewed."},
                    {"agent": "backend", "selected": true, "gate": "backend_change", "reason": "Server behavior changes."},
                    {"agent": "testing", "selected": true, "gate": "behavior_regression", "reason": "Regression risk exists."},
                    {"agent": "documentation", "selected": true, "gate": "durable_artifact", "reason": "Technical specification must be synchronized."}
                  ],
                  "required_disabled_agents": [],
                  "notes": null,
                  "nodes": [
                    {"id": "architecture", "agent": "architecture", "phase": "design", "objective": "Define boundaries", "depends_on": []},
                    {"id": "backend", "agent": "backend", "phase": "implementation", "objective": "Fix data", "depends_on": ["architecture"]},
                    {"id": "testing", "agent": "testing", "phase": "validation", "objective": "Validate behavior", "depends_on": ["backend"]},
                    {"id": "documentation", "agent": "documentation", "phase": "documentation", "objective": "Synchronize technical documentation", "depends_on": ["testing"]}
                  ]
                }""",
                active_agent=agent,
            )

        return ProviderRunResult(
            output=f"completed by {agent.name}",
            active_agent=agent,
        )


def config(enabled):
    return ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=tuple(enabled),
        agents={},
    )


def test_triage_builds_dag_and_runtime_executes_dependencies():
    provider = PlanningProvider()
    kit = DevAgentKit.build(
        config(
            (
                "triage",
                "architecture",
                "backend",
                "testing",
                "documentation",
            )
        ),
        provider,
    )

    plan = kit.plan_task_sync("Fix report")
    result = kit.execute_plan_sync(plan)

    assert result.is_complete
    assert result.trace is not None
    assert result.trace.status == "completed"
    assert result.trace.model_calls == 5
    assert [
        (node.id, node.status)
        for node in result.nodes
    ] == [
        ("architecture", "completed"),
        ("backend", "completed"),
        ("testing", "completed"),
        ("documentation", "completed"),
    ]


def test_disabled_specialist_is_not_silently_replaced():
    provider = PlanningProvider()
    kit = DevAgentKit.build(
        config(("triage", "frontend")),
        provider,
    )
    plan = TaskPlan.from_json(
        """{
          "request": "Redesign screen",
          "profile": {
            "summary": "Redesign screen UX.",
            "classification": "ux_change",
            "risk_flags": ["ux_change"],
            "durable_artifacts": []
          },
          "agent_decisions": [
            {
              "agent": "frontend",
              "selected": false,
              "gate": "frontend_change",
              "reason": "UX definition is blocked first."
            }
          ],
          "required_disabled_agents": ["ux_ui"],
          "nodes": []
        }"""
    )

    try:
        kit.execute_plan_sync(plan)
    except DisabledAgentRequiredError as exc:
        assert exc.agents == ("ux_ui",)
    else:
        raise AssertionError("Expected DisabledAgentRequiredError")
