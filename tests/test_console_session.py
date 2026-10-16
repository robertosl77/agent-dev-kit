import json

import pytest

pytest.importorskip("anthropic")

from test_console_modes import console, git, no_switch, project, runtime_for  # noqa: F401

from agent_dev_kit.console_session import (
    CommandSession,
    cmd_backlog,
    cmd_do,
    cmd_grafo,
    cmd_input,
    cmd_plan,
    cmd_testing,
)


def test_input_only_answers_read_and_accumulates(project):
    session = CommandSession(root=project)
    io_, out = console()

    cmd_input(session, "dato 1", io=io_)
    cmd_input(session, "dato 2", io=io_)

    assert out.getvalue().splitlines() == ["Leído", "Leído"]
    assert session.request == "dato 1\n\ndato 2"
    assert session.plan is None


def test_without_plan_grafo_backlog_and_do_execute_nothing(project):
    runtime, messages = runtime_for(project)
    session = CommandSession(root=project)
    io_, out = console()

    cmd_grafo(session, io=io_)
    cmd_backlog(session, io=io_)
    cmd_do(session, runtime, "", io=io_, confirm_switch=no_switch)

    assert out.getvalue().splitlines() == [
        "No hay plan.",
        "No hay backlog.",
        "No hay plan. Primero /plan y aprobalo.",
    ]
    assert messages.calls == []


def test_plan_uses_accumulated_context_and_does_not_execute(project):
    runtime, messages = runtime_for(project)
    session = CommandSession(root=project)
    io_, out = console("s")

    cmd_input(session, "T-066 README", io=io_)
    cmd_plan(session, runtime, "en español", io=io_, confirm_switch=no_switch)

    assert len(messages.calls) == 1  # only the planner
    assert "T-066 README\\n\\nen español" in json.dumps(messages.calls[0], ensure_ascii=False)
    assert session.agreed is True
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "develop"
    assert git(project, "status", "--porcelain") == ""
    saved = json.loads((project / ".agent-dev-kit/runtime/backlog.json").read_text("utf-8"))
    assert saved["agreed"] is True
    assert saved["nodes"][0]["id"] == "doc-1" and saved["scrum"] is None


def test_replan_is_not_agreed_and_blocks_do(project):
    runtime, messages = runtime_for(project)
    session = CommandSession(root=project)
    io_, out = console("s", "n")

    cmd_plan(session, runtime, "T-066 README", io=io_, confirm_switch=no_switch)
    cmd_plan(session, runtime, "otro detalle", io=io_, confirm_switch=no_switch)
    cmd_do(session, runtime, "", io=io_, confirm_switch=no_switch)

    assert session.agreed is False
    assert "El plan no está acordado." in out.getvalue()
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "develop"


def test_do_executes_the_agreed_plan_without_replanning(project):
    runtime, messages = runtime_for(project)
    session = CommandSession(root=project)
    # plan OK · step OK · commit OK
    io_, out = console("s", "s", "s")

    cmd_plan(session, runtime, "T-066 actualizar README", io=io_, confirm_switch=no_switch)
    planner_calls = sum(
        1 for c in messages.calls if c.get("tool_choice", {}).get("name") == "submit_output"
    )
    cmd_do(session, runtime, "", io=io_, confirm_switch=no_switch)

    assert planner_calls == 1
    assert sum(
        1 for c in messages.calls if c.get("tool_choice", {}).get("name") == "submit_output"
    ) == 1  # /do did not plan again
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "docs/t-066-actualizar-readme"
    assert "develop" in (project / "README.md").read_text(encoding="utf-8")
    io2, out2 = console()
    cmd_backlog(session, io=io2)
    assert "completed" in out2.getvalue()


def test_backlog_and_grafo_survive_a_new_session(project):
    runtime, _ = runtime_for(project)
    first = CommandSession(root=project)
    io_, _ = console("s")
    cmd_plan(first, runtime, "T-066 README", io=io_, confirm_switch=no_switch)

    second = CommandSession(root=project)
    io2, out2 = console()
    cmd_backlog(second, io=io2)
    cmd_grafo(second, io=io2)
    cmd_do(second, runtime, "", io=io2, confirm_switch=no_switch)

    text_out = out2.getvalue()
    assert "doc-1" in text_out and "acordado" in text_out
    assert '"trace"' in text_out
    assert "volvé a correr /plan" in text_out


def test_testing_runs_declared_commands_and_only_reports(project):
    runtime, messages = runtime_for(project)
    session = CommandSession(root=project)
    io_, out = console("lo del README")

    cmd_testing(session, runtime, "", io=io_)

    text_out = out.getvalue()
    assert "Pruebas de: lo del README" in text_out
    assert "→ git status" in text_out and "OK" in text_out
    assert "no se corrigió nada" in text_out
    assert messages.calls == []
    assert git(project, "status", "--porcelain") == ""


def test_testing_without_plan_or_answer_runs_nothing(project):
    runtime, _ = runtime_for(project)
    session = CommandSession(root=project)
    io_, out = console("")

    cmd_testing(session, runtime, "", io=io_)

    assert "No se probó nada." in out.getvalue()


# ------------------------------------------------------------------ Scrum
import copy
from types import SimpleNamespace

from test_console_modes import PLAN, msg, text, tool

from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.project_config import load_project_config
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.providers.provider_anthropic import AnthropicProvider
from agent_dev_kit.workspace_tools import Workspace

SCRUM_PLAN = {
    "request": "App nueva de notas",
    "profile": {
        "summary": "App nueva",
        "classification": "feature",
        "risk_flags": ["user_story_validation"],
        "durable_artifacts": [],
    },
    "agent_decisions": [
        {"agent": "scrum_master", "selected": True, "gate": "user_story_validation", "reason": "HU"},
        {"agent": "documentation", "selected": True, "gate": "docs", "reason": "README"},
        {"agent": "reviewer", "selected": False, "gate": "not_needed", "reason": "demo"},
    ],
    "required_disabled_agents": [],
    "notes": None,
    "nodes": [
        {"id": "sm-1", "agent": "scrum_master", "phase": "intake",
         "objective": "Historias", "depends_on": []},
        {"id": "doc-1", "agent": "documentation", "phase": "documentation",
         "objective": "README", "depends_on": ["sm-1"]},
    ],
}

BACKLOG = {
    "items": [
        {"id": "HU-01", "type": "RF", "title": "Como usuario, quiero crear notas, para recordar",
         "criteria": ["nota creada"], "sprint": 1},
        {"id": "HU-02", "type": "RF", "title": "Como usuario, quiero borrar notas, para limpiar",
         "criteria": ["nota borrada"], "sprint": 1},
        {"id": "RNF-01", "type": "RNF", "title": "Exportar a CSV",
         "criteria": ["archivo CSV"], "sprint": 2},
    ],
    "sprints": [
        {"number": 1, "goal": "Notas", "testable_result": "crear y borrar"},
        {"number": 2, "goal": "Exportar", "testable_result": "CSV"},
    ],
    "definition_of_done": ["Respuesta < 2 s"],
}


class ScrumMessages:
    """First plan uses Scrum; sprint plans are docs-only; backlog is BACKLOG."""

    def __init__(self):
        self.calls = []
        self.plans = 0

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("tool_choice", {}).get("name") == "submit_output":
            schema = json.dumps(kwargs.get("tools", []))
            if '"sprints"' in schema:
                return msg(tool("submit_output", BACKLOG, "b1"), stop="tool_use")
            self.plans += 1
            payload = SCRUM_PLAN if self.plans == 1 else copy.deepcopy(PLAN)
            if self.plans > 1:
                payload["agent_decisions"].append(
                    {"agent": "scrum_master", "selected": False, "gate": "not_needed",
                     "reason": "historias ya aprobadas"})
            return msg(tool("submit_output", payload, f"p{self.plans}"), stop="tool_use")
        tools = {item["name"] for item in kwargs.get("tools", [])}
        turns = sum(1 for m in kwargs["messages"] if m["role"] == "assistant")
        if "replace_in_file" in tools:
            script = [tool("replace_in_file", {"path": "README.md", "old_text": "fix/mvp-funcional",
                                               "new_text": "develop"}, "t1")]
            if turns < len(script):
                return msg(script[turns], stop="tool_use")
            return msg(text("Hecho."))
        return msg(text("ok"))


@pytest.fixture
def scrum_project(project):
    path = project / ".agent-dev-kit" / "project.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "enabled: [triage, documentation, reviewer]",
            "enabled: [triage, scrum_master, documentation, reviewer]",
        ),
        encoding="utf-8",
    )
    git(project, "commit", "-qam", "scrum")
    return project


def scrum_runtime(root):
    messages = ScrumMessages()
    registry = ProviderRegistry()
    registry.register(
        "anthropic",
        lambda config: AnthropicProvider(
            default_model=config.default_model,
            client=SimpleNamespace(messages=messages),
        ),
    )
    config = load_project_config(root)
    runtime = ProviderRuntime(
        registry=registry, project_config=config,
        workspace=Workspace(root, config.workspace), mode="propose",
    )
    return runtime, messages


def test_plan_with_scrum_builds_rf_rnf_backlog_without_executing(scrum_project):
    runtime, messages = scrum_runtime(scrum_project)
    session = CommandSession(root=scrum_project)
    io_, out = console("s")

    cmd_plan(session, runtime, "App nueva de notas", io=io_, confirm_switch=no_switch)

    text_out = out.getvalue()
    assert "Backlog propuesto (Scrum):" in text_out
    assert "HU-01    RF" in text_out and "RNF-01   RNF" in text_out
    assert "Definition of Done" in text_out and "Respuesta < 2 s" in text_out
    assert "¿Aprobás el plan y el backlog?" not in text_out  # asked via input, not printed
    assert session.agreed and session.backlog["sprints"][0]["number"] == 1
    assert len(messages.calls) == 2  # planner + backlog, no node executed
    assert git(scrum_project, "rev-parse", "--abbrev-ref", "HEAD") == "develop"


def test_do_runs_one_sprint_and_allows_moving_items(scrum_project):
    runtime, messages = scrum_runtime(scrum_project)
    session = CommandSession(root=scrum_project)
    io_, _ = console("s")
    cmd_plan(session, runtime, "T-070 App nueva de notas", io=io_, confirm_switch=no_switch)

    # sacar HU-02 → pasa al sprint 2 · ejecutar sprint · OK plan del sprint · commit
    io2, out2 = console("-HU-02", "s", "s", "s")
    cmd_do(session, runtime, "", io=io2, confirm_switch=no_switch)

    text_out = out2.getvalue()
    assert "Sprint 1 — Notas" in text_out
    assert "Sprint 1: se sacaron HU-02." in text_out
    items = {item["id"]: item for item in session.backlog["items"]}
    assert items["HU-01"]["status"] == "done"
    assert items["HU-02"]["sprint"] == 2 and items["HU-02"]["status"] == "pending"
    assert "Sprint 1 terminado" in text_out
    assert session.adjustments == ["Sprint 1: se sacaron HU-02"]
    sprint_prompt = json.dumps(messages.calls[2], ensure_ascii=False)
    assert "Sprint 1" in sprint_prompt and "HU-01" in sprint_prompt and "HU-02" not in sprint_prompt


def test_sprint_backlog_survives_a_new_session(scrum_project):
    runtime, _ = scrum_runtime(scrum_project)
    first = CommandSession(root=scrum_project)
    io_, _ = console("s")
    cmd_plan(first, runtime, "App nueva de notas", io=io_, confirm_switch=no_switch)

    second = CommandSession(root=scrum_project)
    io2, out2 = console("n")
    cmd_backlog(second, io=io2)
    cmd_do(second, runtime, "sprint 2", io=io2, confirm_switch=no_switch)

    text_out = out2.getvalue()
    assert "Backlog (acordado):" in text_out
    assert "Sprint 2 — Exportar" in text_out
    assert "No se ejecutó nada." in text_out


def test_backlog_parser_rejects_bad_shapes():
    from agent_dev_kit.backlog import BacklogError, parse_backlog

    bad = copy.deepcopy(BACKLOG)
    bad["items"][0]["type"] = "FUNC"
    with pytest.raises(BacklogError):
        parse_backlog(bad)
    bad = copy.deepcopy(BACKLOG)
    bad["items"][0]["sprint"] = 9
    with pytest.raises(BacklogError):
        parse_backlog(bad)
    assert parse_backlog(json.dumps(BACKLOG))["items"][0]["status"] == "pending"


def test_preapproved_stories_drop_the_scrum_master_gate():
    from agent_dev_kit.task_plan import TaskPlan

    payload = copy.deepcopy(PLAN)
    payload["request"] = "Crear una pantalla para el usuario"
    payload["agent_decisions"].append(
        {"agent": "scrum_master", "selected": False, "gate": "not_needed", "reason": "aprobadas"})
    plan = TaskPlan.from_payload(payload, require_agent_decisions=True)
    plan.stories_preapproved = True
    plan.validate_orchestration_policy(
        ["triage", "scrum_master", "documentation", "reviewer"],
        request=payload["request"],
    )
    assert "user_story_validation" not in plan.profile.risk_flags

    strict = TaskPlan.from_payload(payload, require_agent_decisions=True)
    with pytest.raises(Exception, match="scrum_master"):
        strict.validate_orchestration_policy(
            ["triage", "scrum_master", "documentation", "reviewer"],
            request=payload["request"],
        )
