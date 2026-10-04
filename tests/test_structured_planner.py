import json

import pytest

from agent_dev_kit.orchestration_policy import RiskFlag, TaskPhase
from agent_dev_kit.planner_contract import (
    PlannerAgentDecision,
    PlannerRequestProfile,
    PlannerTaskNode,
    StructuredTaskPlan,
)
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)
from agent_dev_kit.runtime import DevAgentKit
from agent_dev_kit.task_plan import TaskPlanError


def config():
    return ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=("triage", "backend"),
        agents={},
    )


def valid_payload():
    return {
        "request": "Fix backend behavior",
        "profile": {
            "summary": "Fix backend behavior.",
            "classification": "backend_bug",
            "risk_flags": ["backend_change"],
            "durable_artifacts": [],
        },
        "agent_decisions": [
            {
                "agent": "backend",
                "selected": True,
                "gate": "backend_change",
                "reason": "Backend behavior changes.",
            }
        ],
        "required_disabled_agents": [],
        "notes": None,
        "nodes": [
            {
                "id": "backend",
                "agent": "backend",
                "phase": "implementation",
                "objective": "Fix backend behavior",
                "depends_on": [],
            }
        ],
    }


class StructuredPlanningProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.handoffs = {}
        self.structured_type = None

    def create_agent(self, definition, *, handoffs=(), tools=()):
        handle = AgentHandle(
            provider=self.key,
            name=definition.name,
            native={
                "name": definition.name,
                "handoffs": tuple(item.name for item in handoffs),
            },
        )
        self.handoffs[definition.name] = tuple(item.name for item in handoffs)
        return handle

    def supports_structured_output(self):
        return True

    def create_structured_agent(self, definition, *, output_type):
        self.structured_type = output_type
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native={
                "name": definition.name,
                "handoffs": (),
                "structured": True,
            },
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)
        values = tuple(item.name for item in handoffs)
        agent.native["handoffs"] = values
        self.handoffs[agent.name] = values

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        assert agent.name == "Agent Triage Planner"
        output = StructuredTaskPlan(
            request="Fix backend behavior",
            profile=PlannerRequestProfile(
                summary="Fix backend behavior.",
                classification="backend_bug",
                risk_flags=[RiskFlag.BACKEND_CHANGE],
                durable_artifacts=[],
            ),
            agent_decisions=[
                PlannerAgentDecision(
                    agent="backend",
                    selected=True,
                    gate="backend_change",
                    reason="Backend behavior changes.",
                )
            ],
            required_disabled_agents=[],
            notes=None,
            nodes=[
                PlannerTaskNode(
                    id="backend",
                    agent="backend",
                    phase=TaskPhase.IMPLEMENTATION,
                    objective="Fix backend behavior",
                    depends_on=[],
                )
            ],
        )
        return ProviderRunResult(output=output, active_agent=agent)


class RepairPlanningProvider(AgentProvider):
    key = "fake"

    def __init__(self, *, missing_field_forever=False):
        self.planner_calls = 0
        self.missing_field_forever = missing_field_forever

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native=object(),
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        if agent.name != "Agent Triage Planner":
            return ProviderRunResult(output="done", active_agent=agent)

        self.planner_calls += 1
        if self.missing_field_forever:
            payload = valid_payload()
            payload.pop("notes")
            return ProviderRunResult(
                output=json.dumps(payload),
                active_agent=agent,
            )

        if self.planner_calls == 1:
            return ProviderRunResult(
                output="{not valid json",
                active_agent=agent,
            )

        return ProviderRunResult(
            output=json.dumps(valid_payload()),
            active_agent=agent,
        )


class HandoffPlanningProvider(RepairPlanningProvider):
    def __init__(self):
        super().__init__()
        self.backend_handle = None

    def create_agent(self, definition, *, handoffs=(), tools=()):
        handle = super().create_agent(
            definition,
            handoffs=handoffs,
            tools=tools,
        )
        if definition.name == "Agent Backend":
            self.backend_handle = handle
        return handle

    def run_sync(self, agent, message, *, session=None):
        if agent.name == "Agent Triage Planner":
            self.planner_calls += 1
            return ProviderRunResult(
                output=json.dumps(valid_payload()),
                active_agent=self.backend_handle,
            )
        return ProviderRunResult(output="done", active_agent=agent)


def test_structured_planner_is_isolated_from_conversation_handoffs():
    provider = StructuredPlanningProvider()
    kit = DevAgentKit.build(config(), provider)

    plan = kit.plan_task_sync("Fix backend behavior")

    assert provider.structured_type is StructuredTaskPlan
    assert kit.planner_agent.name == "Agent Triage Planner"
    assert kit.planner_agent.native["handoffs"] == ()
    assert provider.handoffs["Agent Triage"] == ("Agent Backend",)
    assert plan.nodes[0].agent == "backend"
    assert plan.trace.model_calls == 1


def test_invalid_json_gets_exactly_one_controlled_repair():
    provider = RepairPlanningProvider()
    kit = DevAgentKit.build(config(), provider)

    plan = kit.plan_task_sync("Fix backend behavior")

    assert provider.planner_calls == 2
    assert plan.trace.model_calls == 2
    assert plan.nodes[0].agent == "backend"


def test_missing_required_field_fails_after_one_repair_attempt():
    provider = RepairPlanningProvider(missing_field_forever=True)
    kit = DevAgentKit.build(config(), provider)

    with pytest.raises(TaskPlanError, match="after one repair attempt"):
        kit.plan_task_sync("Fix backend behavior")

    assert provider.planner_calls == 2


def test_unexpected_planner_handoff_is_rejected_without_repair():
    provider = HandoffPlanningProvider()
    kit = DevAgentKit.build(config(), provider)

    with pytest.raises(TaskPlanError, match="handed off unexpectedly"):
        kit.plan_task_sync("Fix backend behavior")

    assert provider.planner_calls == 1
