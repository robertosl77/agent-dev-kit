"""MCP workflows exercise the same DAG, workspace and Git policy as CLI."""

import json
import subprocess

import pytest

from agent_dev_kit.gateway import AgentDevKitGateway
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider, ProviderRunResult


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True,
        capture_output=True, text=True,
    ).stdout.strip()


class WorkflowFakeProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.ran = []

    def native_tool(self, tool):
        return tool

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(
            provider=self.key, name=definition.name,
            native={"tools": tuple(tool.native for tool in tools)},
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        self.ran.append(agent.name)
        if agent.name == "Agent Triage Planner":
            return ProviderRunResult(
                output=json.dumps({
                    "request": "Cambiar opción de moneda",
                    "profile": {
                        "summary": "Permitir cambiar moneda.",
                        "classification": "feature",
                        "risk_flags": ["frontend_change", "user_story_validation"],
                        "durable_artifacts": [],
                    },
                    "agent_decisions": [
                        {"agent": "frontend", "selected": True, "gate": "frontend_change",
                         "reason": "Cambio visible del formulario."},
                        {"agent": "scrum_master", "selected": True,
                         "gate": "user_story_validation",
                         "reason": "Definir historia y criterios."},
                    ],
                    "required_disabled_agents": [], "notes": None,
                    "nodes": [
                        {"id": "story", "agent": "scrum_master", "phase": "discovery",
                         "objective": "Acordar historia y criterios", "depends_on": []},
                        {"id": "frontend", "agent": "frontend", "phase": "implementation",
                         "objective": "Cambiar formulario", "depends_on": ["story"]},
                    ],
                }),
                active_agent=agent,
            )
        if agent.name == "Agent Scrum Master":
            return ProviderRunResult(
                output="HU: seleccionar moneda. ¿Símbolo o conversión? Criterios a confirmar.",
                active_agent=agent,
            )
        if agent.name == "Agent Frontend":
            for tool in agent.native["tools"]:
                if tool.name == "write_file":
                    tool.handler({"path": "form.txt", "content": "selector moneda"})
            return ProviderRunResult(output="Implementación simulada.", active_agent=agent)
        return ProviderRunResult(output="ok", active_agent=agent)


@pytest.fixture
def setup_repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "develop")
    git(tmp_path, "config", "user.email", "test@example.org")
    git(tmp_path, "config", "user.name", "Test")
    d = tmp_path / ".agent-dev-kit"
    d.mkdir()
    (d / "project.yaml").write_text("""project:
  name: MCPDemo
provider:
  name: fake
agents:
  enabled: [triage, scrum_master, frontend]
git_workflow:
  branches: {production: main, integration: develop}
  protected: [main, develop]
  task_branch: {base: develop, naming: "{kind}/{issue}-{slug}"}
  pull_requests:
    task_target: develop
    release_source: develop
    release_target: main
    require_issue_reference: true
""", encoding="utf-8")
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "initial")
    registry = ProviderRegistry()
    provider = WorkflowFakeProvider()
    registry.register("fake", lambda config: provider)
    gateway = AgentDevKitGateway(tmp_path, registry=registry)
    return gateway, provider, tmp_path


REQUEST = "T-101 Agregar una opción de moneda al formulario"


def test_plan_does_not_execute_specialists(setup_repo):
    gateway, provider, _ = setup_repo
    outcome = gateway.workflow.start(REQUEST, mode="plan")
    assert outcome["status"] == "completed"
    assert outcome["plan"]["nodes"][0]["agent"] == "scrum_master"
    assert provider.ran == ["Agent Triage Planner"]


def test_proposal_requires_explicit_story_approval(setup_repo):
    gateway, provider, root = setup_repo
    first = gateway.workflow.start(REQUEST, mode="propose")
    assert first["status"] == "approval_required"
    assert first["approval"]["kind"] == "story"
    assert provider.ran == ["Agent Triage Planner", "Agent Scrum Master"]
    workflow_id = first["workflow_id"]
    with pytest.raises(ValueError, match="matching outstanding"):
        gateway.workflow.decide(workflow_id, "wrong-id", True)
    assert not (root / "form.txt").exists()
    approved = gateway.workflow.decide(
        workflow_id, first["approval"]["id"], True
    )
    assert approved["status"] == "completed"
    assert provider.ran[-1] == "Agent Frontend"
    assert not (root / "form.txt").exists()
    with pytest.raises(ValueError, match="matching outstanding"):
        gateway.workflow.decide(workflow_id, first["approval"]["id"], True)


def test_rejected_story_stops_before_frontend(setup_repo):
    gateway, provider, root = setup_repo
    first = gateway.workflow.start(REQUEST, mode="propose")
    rejected = gateway.workflow.decide(
        first["workflow_id"], first["approval"]["id"], False,
    )
    assert rejected["status"] == "rejected"
    assert "Agent Frontend" not in provider.ran
    assert git(root, "branch", "--show-current") == "develop"


def test_act_is_disabled_by_default(setup_repo):
    gateway, _, root = setup_repo
    response = gateway.workflow.start(REQUEST, mode="act")
    assert response["status"] == "blocked"
    assert git(root, "branch", "--show-current") == "develop"


def test_action_requires_separate_plan_story_and_commit_approvals(setup_repo):
    gateway, provider, root = setup_repo
    gateway.workflow.allow_actions = True
    response = gateway.workflow.start(REQUEST, mode="act")
    assert response["approval"]["kind"] == "plan"
    assert git(root, "branch", "--show-current") == "develop"
    response = gateway.workflow.decide(
        response["workflow_id"], response["approval"]["id"], True
    )
    assert response["approval"]["kind"] == "story"
    assert not (root / "form.txt").exists()
    response = gateway.workflow.decide(
        response["workflow_id"], response["approval"]["id"], True
    )
    assert response["approval"]["kind"] == "commit"
    assert (root / "form.txt").read_text() == "selector moneda"
    assert "form.txt" in "\n".join(response["review"]["changed_files"])
    assert git(root, "log", "-1", "--format=%s") == "initial"
    response = gateway.workflow.decide(
        response["workflow_id"], response["approval"]["id"], True
    )
    assert response["status"] == "completed"
    assert git(root, "log", "-1", "--format=%s").startswith("T-101:")
    assert git(root, "branch", "--show-current").startswith("feat/t-101-")


def test_rejected_plan_never_creates_branch(setup_repo):
    gateway, provider, root = setup_repo
    gateway.workflow.allow_actions = True
    response = gateway.workflow.start(REQUEST, mode="act")
    rejected = gateway.workflow.decide(
        response["workflow_id"], response["approval"]["id"], False
    )
    assert rejected["status"] == "rejected"
    assert "Agent Scrum Master" not in provider.ran
    assert git(root, "branch", "--show-current") == "develop"


def test_modified_diff_invalidates_old_commit_approval(setup_repo):
    gateway, _, root = setup_repo
    gateway.workflow.allow_actions = True
    result = gateway.workflow.start(REQUEST, mode="act")
    result = gateway.workflow.decide(result["workflow_id"], result["approval"]["id"], True)
    result = gateway.workflow.decide(result["workflow_id"], result["approval"]["id"], True)
    assert result["approval"]["kind"] == "commit"
    prior_decision = result["approval"]["id"]
    (root / "form.txt").write_text("unexpected change", encoding="utf-8")

    refreshed = gateway.workflow.decide(result["workflow_id"], prior_decision, True)
    assert refreshed["approval"]["kind"] == "commit"
    assert refreshed["approval"]["id"] != prior_decision
    assert refreshed["status"] == "approval_required"
    assert git(root, "log", "-1", "--format=%s") == "initial"


def test_two_action_sessions_cannot_mutate_one_worktree(setup_repo):
    gateway, _, root = setup_repo
    gateway.workflow.allow_actions = True
    first = gateway.workflow.start(REQUEST, mode="act")
    assert first["status"] == "approval_required"
    second = gateway.workflow.start(REQUEST, mode="act")
    assert second["status"] == "blocked"
    assert "Another action workflow" in second["reason"]
    gateway.workflow.cancel(first["workflow_id"])
    third = gateway.workflow.start(REQUEST, mode="act")
    assert third["status"] == "approval_required"


def test_usage_and_graphs_are_read_only(setup_repo):
    gateway, _, root = setup_repo
    result = gateway.workflow.start(REQUEST, mode="plan")
    data = gateway.workflow.usage(result["workflow_id"])
    assert data["totals"]["requests"] == 0  # scripted provider has no token usage
    assert "estimated_usd" in data
    assert isinstance(gateway.workflow.graphs()["runs"], list)
    assert isinstance(gateway.workflow.candidates()["report"], list)
    assert git(root, "branch", "--show-current") == "develop"


def test_commit_rejects_branch_switched_after_approval(setup_repo):
    gateway, _, root = setup_repo
    gateway.workflow.allow_actions = True
    result = gateway.workflow.start(REQUEST, mode="act")
    result = gateway.workflow.decide(
        result["workflow_id"], result["approval"]["id"], True,
    )
    result = gateway.workflow.decide(
        result["workflow_id"], result["approval"]["id"], True,
    )
    assert result["approval"]["kind"] == "commit"
    git(root, "checkout", "-q", "-b", "main")
    denied = gateway.workflow.decide(
        result["workflow_id"], result["approval"]["id"], True,
    )
    assert denied["status"] == "failed"
    assert "differs from authorized" in denied["failure"]
    assert git(root, "branch", "--show-current") == "main"
    assert git(root, "log", "-1", "--format=%s") == "initial"
