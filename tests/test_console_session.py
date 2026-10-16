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
    assert saved["backlog"][0]["id"] == "doc-1"


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
