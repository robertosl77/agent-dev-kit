import json

import pytest

from agent_dev_kit.orchestration import (
    AgentGateDecision,
    OrchestrationTrace,
    RequestProfile,
    orchestration_config_from_mapping,
)
from agent_dev_kit.orchestration_budget import OrchestrationBudgetExceeded
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)
from agent_dev_kit.runtime import DevAgentKit
from agent_dev_kit.task_plan import TaskPlan


class BudgetProvider(AgentProvider):
    key = "fake"

    def __init__(self, *, fail_first_backend=False):
        self.calls = []
        self.fail_first_backend = fail_first_backend
        self.failed = False

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native={"name": definition.name},
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        self.calls.append((agent.name, message))
        if (
            self.fail_first_backend
            and agent.name == "Agent Backend"
            and not self.failed
        ):
            self.failed = True
            raise RuntimeError("simulated provider interruption")

        if agent.name == "Agent Triage Planner":
            payload = {
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
                        "objective": "Fix behavior",
                        "depends_on": [],
                    }
                ],
            }
            return ProviderRunResult(
                output=json.dumps(payload),
                active_agent=agent,
            )

        return ProviderRunResult(
            output=f"result:{agent.name}",
            active_agent=agent,
        )


def make_config(*, enabled=("backend",), budgets=None):
    return ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=tuple(enabled),
        agents={},
        orchestration=orchestration_config_from_mapping(
            {"budgets": budgets or {}}
        ),
    )


def backend_plan(nodes):
    return TaskPlan.from_payload(
        {
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
            "nodes": nodes,
        },
        require_agent_decisions=True,
    )


def attach_trace(plan):
    plan.trace = OrchestrationTrace(
        request_summary=plan.profile.summary,
        request_fingerprint="test",
        classification=plan.profile.classification,
        risk_flags=plan.profile.risk_flags,
        durable_artifacts=plan.profile.durable_artifacts,
        agent_decisions=plan.agent_decisions,
        dag=(),
    )


def test_dag_budget_blocks_before_any_provider_call():
    provider = BudgetProvider()
    kit = DevAgentKit.build(
        make_config(budgets={"max_dag_nodes": 1}),
        provider,
    )
    plan = backend_plan(
        [
            {
                "id": "one",
                "agent": "backend",
                "phase": "implementation",
                "objective": "First change",
                "depends_on": [],
            },
            {
                "id": "two",
                "agent": "backend",
                "phase": "implementation",
                "objective": "Second change",
                "depends_on": ["one"],
            },
        ]
    )

    with pytest.raises(OrchestrationBudgetExceeded) as exc:
        kit.execute_plan_sync(plan)

    assert exc.value.budget == "max_dag_nodes"
    assert exc.value.status == "requires_human_approval"
    assert plan.execution_status == "requires_human_approval"
    assert provider.calls == []


def test_provider_call_budget_includes_planning_call():
    provider = BudgetProvider()
    kit = DevAgentKit.build(
        make_config(
            enabled=("triage", "backend"),
            budgets={"max_provider_calls": 1},
        ),
        provider,
    )

    plan = kit.plan_task_sync("Fix backend behavior")

    assert plan.provider_calls == 1

    with pytest.raises(OrchestrationBudgetExceeded) as exc:
        kit.execute_plan_sync(plan)

    assert exc.value.budget == "max_provider_calls"
    assert exc.value.actual == 2
    assert len(provider.calls) == 1
    assert plan.node("backend").status == "blocked"


def test_duplicate_node_input_reuses_completed_output_without_provider_call():
    provider = BudgetProvider()
    kit = DevAgentKit.build(
        make_config(budgets={"max_provider_calls": 1}),
        provider,
    )
    plan = backend_plan(
        [
            {
                "id": "first",
                "agent": "backend",
                "phase": "implementation",
                "objective": "Apply identical change",
                "depends_on": [],
            },
            {
                "id": "second",
                "agent": "backend",
                "phase": "implementation",
                "objective": "Apply identical change",
                "depends_on": [],
            },
        ]
    )
    attach_trace(plan)

    result = kit.execute_plan_sync(plan)

    assert result.is_complete
    assert len(provider.calls) == 1
    assert plan.calls_avoided_by_reuse == 1
    assert plan.trace.calls_avoided_by_reuse == 1
    assert plan.node("second").output == plan.node("first").output
    assert plan.node("second").evidence["reused_from"] == "first"


def test_revisit_budget_blocks_retry_before_second_provider_call():
    provider = BudgetProvider(fail_first_backend=True)
    kit = DevAgentKit.build(
        make_config(budgets={"max_revisits": 0}),
        provider,
    )
    plan = backend_plan(
        [
            {
                "id": "backend",
                "agent": "backend",
                "phase": "implementation",
                "objective": "Fix behavior",
                "depends_on": [],
            }
        ]
    )
    attach_trace(plan)

    with pytest.raises(RuntimeError, match="simulated"):
        kit.execute_plan_sync(plan)

    assert len(provider.calls) == 1
    assert plan.node("backend").status == "pending"

    with pytest.raises(OrchestrationBudgetExceeded) as exc:
        kit.execute_plan_sync(plan)

    assert exc.value.budget == "max_revisits"
    assert len(provider.calls) == 1
    assert plan.node("backend").status == "blocked"


def test_dependency_context_is_deduplicated_and_truncated_locally():
    provider = BudgetProvider()
    kit = DevAgentKit.build(
        make_config(
            budgets={
                "max_context_chars": 1200,
                "max_dependency_evidence_chars": 120,
            }
        ),
        provider,
    )
    plan = backend_plan(
        [
            {
                "id": "source_a",
                "agent": "backend",
                "phase": "implementation",
                "objective": "Produce source",
                "depends_on": [],
            },
            {
                "id": "source_b",
                "agent": "backend",
                "phase": "implementation",
                "objective": "Produce other source",
                "depends_on": [],
            },
            {
                "id": "target",
                "agent": "backend",
                "phase": "validation",
                "objective": "Consume evidence",
                "depends_on": ["source_a", "source_b"],
            },
        ]
    )
    repeated = "same evidence " * 80
    plan.node("source_a").status = "completed"
    plan.node("source_a").output = repeated
    plan.node("source_b").status = "completed"
    plan.node("source_b").output = repeated
    attach_trace(plan)

    kit.execute_plan_sync(plan)

    assert len(provider.calls) == 1
    prompt = provider.calls[0][1]
    assert len(prompt) <= 1200
    assert "truncated by orchestration budget" in prompt
    assert plan.trace.deduplicated_context_items == 1
    assert plan.trace.context_truncations == 1
    assert plan.trace.max_context_chars_observed <= 1200


class OversizedPlannerProvider(BudgetProvider):
    def run_sync(self, agent, message, *, session=None):
        if agent.name != "Agent Triage Planner":
            return super().run_sync(agent, message, session=session)

        self.calls.append((agent.name, message))
        payload = {
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
                    "id": "one",
                    "agent": "backend",
                    "phase": "implementation",
                    "objective": "First change",
                    "depends_on": [],
                },
                {
                    "id": "two",
                    "agent": "backend",
                    "phase": "implementation",
                    "objective": "Second change",
                    "depends_on": ["one"],
                },
            ],
        }
        return ProviderRunResult(
            output=json.dumps(payload),
            active_agent=agent,
        )


def test_oversized_planner_dag_is_rejected_before_execution():
    provider = OversizedPlannerProvider()
    kit = DevAgentKit.build(
        make_config(
            enabled=("triage", "backend"),
            budgets={"max_dag_nodes": 1},
        ),
        provider,
    )

    with pytest.raises(OrchestrationBudgetExceeded) as exc:
        kit.plan_task_sync("Fix backend behavior")

    assert exc.value.budget == "max_dag_nodes"
    assert exc.value.stage == "planning"
    assert len(provider.calls) == 1
