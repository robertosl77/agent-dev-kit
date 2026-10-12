"""Scrum Master: routing, story contract and human approval gate."""

import pytest

from agent_dev_kit.agent_catalog import AGENT_BUILDERS, build_enabled_definitions
from agent_dev_kit.orchestration import AgentGateDecision, RequestProfile
from agent_dev_kit.orchestration_policy import RiskFlag, preclassify_request
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider, ProviderRunResult
from agent_dev_kit.runtime import DevAgentKit
from agent_dev_kit.task_plan import TaskNode, TaskPlan, TaskPlanError
from agent_dev_kit.workspace_tools import agent_access


REQUEST = "Necesito agregarle al formulario una opción para cambiar la moneda"


class FakeProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.ran = []

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(provider=self.key, name=definition.name, native=definition)

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        self.ran.append(agent.name)
        output = (
            "HU-001: Como usuario, quiero elegir una moneda.\n"
            "Criterios: selector en el formulario.\n"
            "¿Cambiar símbolo o convertir importes? Confirmación pendiente."
            if agent.name == "Agent Scrum Master"
            else "Cambio implementado (simulado)."
        )
        return ProviderRunResult(output=output, active_agent=agent)


def config(*enabled):
    return ProjectAgentDevKitConfig(
        name="Test",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=tuple(enabled),
        agents={},
    )


def plan(*, dependent=True, with_story=True):
    nodes = (
        [TaskNode(id="story", agent="scrum_master", objective="Proponer HU y criterios", phase="discovery")]
        if with_story else []
    )
    nodes.append(TaskNode(
        id="frontend", agent="frontend", objective="Implementar selector",
        depends_on=("story",) if dependent and with_story else (),
    ))
    decisions = [
        AgentGateDecision(agent="frontend", selected=True, gate="frontend_change",
                          reason="Modificación de formulario."),
    ]
    if with_story:
        decisions.insert(
            0,
            AgentGateDecision(agent="scrum_master", selected=True,
                              gate="user_story_validation", reason="Acordar la funcionalidad."),
        )
    return TaskPlan(
        request=REQUEST,
        nodes=nodes,
        profile=RequestProfile(summary=REQUEST, classification="feature"),
        agent_decisions=tuple(decisions),
        decisions_explicit=True,
    )


def test_scrum_registered_and_read_only():
    assert "scrum_master" in AGENT_BUILDERS
    definition = build_enabled_definitions(config("scrum_master"))["scrum_master"]
    assert definition.name == "Agent Scrum Master"
    assert "currency selector" in definition.instructions
    assert "acceptance criteria" in definition.instructions
    assert agent_access("scrum_master", None) == "read"


def test_small_feature_classified_without_requiring_scrum_for_bugfix():
    assert RiskFlag.USER_STORY_VALIDATION.value in preclassify_request(REQUEST)
    assert RiskFlag.USER_STORY_VALIDATION.value not in preclassify_request(
        "Fix internal cache key regression"
    )


def test_missing_scrum_decision_is_rejected_when_enabled():
    task = plan(with_story=False)
    task.agent_decisions += (
        AgentGateDecision(agent="scrum_master", selected=False,
                          gate="user_story_validation", reason="Omitido."),
    )
    with pytest.raises(TaskPlanError, match="scrum_master"):
        task.validate_orchestration_policy(("scrum_master", "frontend"))


def test_old_consumer_without_scrum_stays_compatible():
    task = plan(with_story=False)
    task.validate_orchestration_policy(("frontend",))
    assert RiskFlag.USER_STORY_VALIDATION.value not in task.profile.risk_flags


def test_no_downstream_node_can_bypass_story():
    task = plan(dependent=False)
    with pytest.raises(TaskPlanError, match="depend on its story intake"):
        task.validate_orchestration_policy(("scrum_master", "frontend"))


def test_explicit_human_approval_required_for_sync_runtime():
    provider = FakeProvider()
    kit = DevAgentKit.build(config("scrum_master", "frontend"), provider)
    task = plan()

    with pytest.raises(TaskPlanError, match="explicit human approval"):
        kit.execute_plan_sync(task)
    assert provider.ran == []

    kit.execute_plan_sync(task, intake_only=True)
    assert provider.ran == ["Agent Scrum Master"]
    assert task.execution_status == "awaiting_story_approval"
    assert task.node("frontend").status == "pending"
    assert not task.story_approved

    with pytest.raises(TaskPlanError, match="explicit human approval"):
        kit.execute_plan_sync(task)
    assert provider.ran == ["Agent Scrum Master"]

    task.story_approved = True
    kit.execute_plan_sync(task)
    assert provider.ran == ["Agent Scrum Master", "Agent Frontend"]
    assert task.is_complete
