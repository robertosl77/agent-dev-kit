"""Prevent /do plans from promising unsupported remote Git operations.

Regression for the rejected real T-066 plan: Triage asked Documentation to
open a PR and Reviewer to review it, although the /do host only creates a
local branch and an approved local commit.
"""
import asyncio
import json

import pytest

from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import (
    AgentHandle, AgentProvider, ProviderRunResult,
)
from agent_dev_kit.runtime import DevAgentKit
from agent_dev_kit.task_plan import (
    TaskPlan, TaskPlanError, build_planning_prompt, validate_act_plan_capabilities,
)


def payload(*, remote=True):
    if remote:
        doc_objective = (
            "On a branch docs/117-readme-t066 (base: develop), audit README.md "
            "and correct only evidence-backed requirements. Open a PR targeting "
            "develop referencing #117."
        )
        review_objective = (
            "Review the PR from docs/117-readme-t066; approve or request changes."
        )
    else:
        doc_objective = (
            "Audit README.md against #117 and the project rules; edit only "
            "the locally verifiable gaps. Do not create a PR."
        )
        review_objective = (
            "Review the local git diff and check each edit against acceptance "
            "criteria; report findings before the host requests commit approval."
        )

    return {
        "request": "Update README for issue #117 (T-066)",
        "profile": {
            "summary": "Document the current branch workflow.",
            "classification": "documentation",
            "risk_flags": [],
            "durable_artifacts": [],
        },
        "agent_decisions": [
            {"agent": "documentation", "selected": True, "gate": "docs",
             "reason": "README changes"},
            {"agent": "reviewer", "selected": True, "gate": "review",
             "reason": "Check documented workflow"},
        ],
        "required_disabled_agents": [],
        "notes": None,
        "nodes": [
            {"id": "documentation-1", "agent": "documentation",
             "phase": "documentation", "objective": doc_objective,
             "depends_on": []},
            {"id": "reviewer-1", "agent": "reviewer", "phase": "review",
             "objective": review_objective,
             "depends_on": ["documentation-1"]},
        ],
    }


def config():
    return ProjectAgentDevKitConfig(
        name="LibreriaIngles test",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=("triage", "documentation", "reviewer"),
        agents={},
    )


class Planner(AgentProvider):
    key = "fake"

    def __init__(self, repair=True):
        self.repair = repair
        self.prompts = []

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(provider=self.key, name=definition.name, native=object())

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    def run_sync(self, agent, message, *, session=None):
        assert agent.name == "Agent Triage Planner"
        self.prompts.append(message)
        is_repaired = self.repair and len(self.prompts) == 2
        return ProviderRunResult(
            output=json.dumps(payload(remote=not is_repaired)),
            active_agent=agent,
        )

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)


def test_act_prompt_describes_actual_local_host_capabilities():
    prompt = build_planning_prompt(
        "Update README for issue #117",
        enabled_agents=("triage", "documentation", "reviewer"),
        available_agents=("triage", "documentation", "reviewer"),
        mode="act",
    )
    assert "This host creates ONE local task branch" in prompt
    assert "It does NOT review a GitHub PR" in prompt
    assert "NO git push, pull-request creation/submission/review/approval/merge" in prompt
    assert "Create independent branches" not in prompt


@pytest.mark.parametrize("objective", [
    "Open a PR targeting develop referencing #117.",
    "Review the PR from docs/117-readme-t066.",
    "Approve the pull request when tests pass.",
    "Crear un PR hacia develop.",
    "Revisar la pull request y aprobarla.",
    "git push origin develop",
    "Create a local commit and push to origin.",
    "Create a task branch docs/117-readme-t066.",
    "On a branch docs/117-readme-t066, update README.",
])
def test_act_rejects_host_or_remote_operations_in_nodes(objective):
    plan = TaskPlan.from_payload(payload(remote=False))
    plan.nodes[0].objective = objective
    with pytest.raises(TaskPlanError, match="unavailable /do operation"):
        validate_act_plan_capabilities(plan)


def test_act_allows_local_review_and_explicit_prohibitions():
    plan = TaskPlan.from_payload(payload(remote=False))
    validate_act_plan_capabilities(plan)
    assert len(plan.nodes) == 2


def test_act_planner_repairs_real_pr_plan_before_user_approval():
    provider = Planner()
    kit = DevAgentKit.build(config(), provider, mode="act")

    result = kit.plan_task_sync(payload()["request"])

    assert len(provider.prompts) == 2
    assert "This host creates ONE local task branch" in provider.prompts[0]
    assert "Validation error:" in provider.prompts[1]
    assert "unavailable /do operation" in provider.prompts[1]
    assert "NO git push" in provider.prompts[1]
    assert all("Open a PR" not in node.objective for node in result.nodes)
    assert "local git diff" in result.nodes[1].objective
    assert result.provider_calls == 2


def test_act_planner_fails_closed_after_one_invalid_repair():
    provider = Planner(repair=False)
    kit = DevAgentKit.build(config(), provider, mode="act")

    with pytest.raises(TaskPlanError, match="after one repair attempt"):
        kit.plan_task_sync(payload()["request"])

    assert len(provider.prompts) == 2


def test_act_async_planner_applies_same_guard():
    provider = Planner()
    kit = DevAgentKit.build(config(), provider, mode="act")

    result = asyncio.run(kit.plan_task(payload()["request"]))

    assert result.provider_calls == 2
    assert "local git diff" in result.nodes[1].objective


def test_act_execute_rejects_bypassed_unchecked_plan():
    provider = Planner()
    kit = DevAgentKit.build(config(), provider, mode="act")
    plan = TaskPlan.from_payload(payload(remote=True))

    with pytest.raises(TaskPlanError, match="unavailable /do operation"):
        kit.execute_plan_sync(plan)

    assert provider.prompts == []


def test_other_modes_do_not_restrict_plans_with_github_pr_analysis():
    prompt = build_planning_prompt(
        "Analyze the PR's documentation",
        enabled_agents=("triage", "documentation", "reviewer"),
        available_agents=("triage", "documentation", "reviewer"),
    )
    assert "This host creates ONE local task branch" not in prompt
    provider = Planner(repair=False)
    kit = DevAgentKit.build(config(), provider, mode="propose")
    result = kit.plan_task_sync(payload()["request"])
    assert result.provider_calls == 1
