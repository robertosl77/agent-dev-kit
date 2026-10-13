import io
import subprocess
from types import SimpleNamespace

import pytest

pytest.importorskip("anthropic")

from agent_dev_kit.console_modes import ConsoleIO, run_act, run_plan_only, run_propose
from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.orchestration import OrchestrationTraceStore
from agent_dev_kit.project_config import load_project_config
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.providers.provider_anthropic import AnthropicProvider
from agent_dev_kit.workspace_tools import Workspace

AGENTS = ["documentation", "reviewer"]

PLAN = {
    "request": "T-066 README",
    "profile": {
        "summary": "Actualizar README.",
        "classification": "documentation",
        "risk_flags": [],
        "durable_artifacts": [],
    },
    "agent_decisions": [
        {"agent": "documentation", "selected": True, "gate": "docs", "reason": "README"},
        {"agent": "reviewer", "selected": False, "gate": "not_needed", "reason": "doc menor"},
    ],
    "required_disabled_agents": [],
    "notes": None,
    "nodes": [
        {
            "id": "doc-1",
            "agent": "documentation",
            "phase": "documentation",
            "objective": "Actualizar README",
            "depends_on": [],
        }
    ],
}


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def usage(model="claude-test"):
    return SimpleNamespace(input_tokens=1000, output_tokens=200,
                           cache_read_input_tokens=0, cache_creation_input_tokens=0)


def msg(*blocks, stop="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=usage(), model="claude-test")


def tool(name, args, call_id):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=args)


def text(value):
    return SimpleNamespace(type="text", text=value)


class ScriptedMessages:
    """Planner returns PLAN; Documentation reads, edits, runs tests, answers."""

    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("tool_choice", {}).get("name") == "submit_output":
            return msg(tool("submit_output", PLAN, "p1"), stop="tool_use")
        tools = {item["name"] for item in kwargs.get("tools", [])}
        turns = sum(1 for m in kwargs["messages"] if m["role"] == "assistant")
        if "replace_in_file" in tools:  # action mode
            script = [
                tool("read_file", {"path": "README.md"}, "t1"),
                tool("replace_in_file", {"path": "README.md", "old_text": "fix/mvp-funcional",
                                         "new_text": "develop"}, "t2"),
                tool("run_command", {"command": "git status --short"}, "t3"),
            ]
            if turns < len(script):
                return msg(script[turns], stop="tool_use")
            return msg(text("README actualizado."))
        if turns == 0 and "read_file" in tools:  # propose mode: inspects first
            return msg(tool("read_file", {"path": "README.md"}, "r1"), stop="tool_use")
        return msg(text("Propuesta basada en el README real."))


@pytest.fixture
def project(tmp_path):
    root = tmp_path
    git(root, "init", "-q", "-b", "develop")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "README.md").write_text("Rama actual: fix/mvp-funcional\n", encoding="utf-8")
    (root / ".agent-dev-kit").mkdir()
    (root / ".agent-dev-kit" / "project.yaml").write_text(
        """project:
  name: Demo
  language: es
provider:
  name: anthropic
  default_model: claude-test
git_workflow:
  branches: {production: main, integration: develop}
  protected: [main, develop]
workspace:
  test_commands: ["git status"]
pricing:
  claude-test: {input_per_mtok: 1.0, output_per_mtok: 5.0}
agents:
  enabled: [triage, documentation, reviewer]
""",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(".agent-dev-kit/runtime/\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


def runtime_for(root, mode="propose"):
    messages = ScriptedMessages()
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
        registry=registry,
        project_config=config,
        workspace=Workspace(root, config.workspace),
        mode=mode,
    )
    return runtime, messages


def console(*answers):
    out = io.StringIO()
    answers = list(answers)
    return ConsoleIO(input_fn=lambda prompt: answers.pop(0), out=out), out


def no_switch(*args):
    return False


def traces(root):
    return OrchestrationTraceStore(root / ".agent-dev-kit/runtime/orchestration-traces.jsonl").read()


def test_plan_only_does_not_run_agents_and_logs_graph(project):
    runtime, messages = runtime_for(project)
    io_, out = console()

    run_plan_only(runtime, "T-066 README", io=io_, confirm_switch=no_switch)

    assert len(messages.calls) == 1  # only the planner
    text_out = out.getvalue()
    assert "doc-1 · documentation" in text_out
    assert "1 de 2 habilitados" in text_out
    assert "consumo: planner 1.000 in / 200 out" in text_out
    assert "USD 0,0020" in text_out
    record = traces(project)[-1]
    assert record["status"] == "planned_only"
    assert record["usage"][0]["stage"] == "planner"
    assert record["intake_key"] and record["model"] == "claude-test"


def test_propose_reads_repo_but_does_not_change_it(project):
    runtime, messages = runtime_for(project)
    io_, out = console()

    run_propose(runtime, "T-066 README", io=io_, confirm_switch=no_switch)

    node_call = messages.calls[1]
    names = {item["name"] for item in node_call["tools"]}
    assert "read_file" in names and "write_file" not in names
    system = node_call["system"][0]["text"]
    assert "Spanish (es)" in system
    prompt = node_call["messages"][0]["content"][0]["text"]
    assert "Original request from the person" in prompt and "T-066 README" in prompt
    assert "Do not invent people, roles" in prompt
    assert "Task plan decided by Triage" in prompt
    assert "Selected agents:\n- documentation:" in prompt
    assert "Nodes:\n- doc-1 [documentation," in prompt
    assert "Propuesta basada en el README real." in out.getvalue()
    assert git(project, "status", "--porcelain") == ""
    record = traces(project)[-1]
    assert record["tool_events"][0]["tool"] == "read_file"
    assert [u["stage"] for u in record["usage"]] == ["planner", "doc-1"]


def test_act_creates_branch_changes_files_runs_tests_and_commits(project):
    runtime, messages = runtime_for(project)
    io_, out = console("s", "s")

    outcome = run_act(runtime, "T-066 actualizar README", io=io_, confirm_switch=no_switch)

    assert outcome.status == "committed"
    assert outcome.branch == "docs/t-066-actualizar-readme"
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == outcome.branch
    assert "develop" in (project / "README.md").read_text(encoding="utf-8")
    assert git(project, "log", "-1", "--format=%s") == "T-066: actualizar README"
    assert git(project, "status", "--porcelain") == ""
    text_out = out.getvalue()
    assert "Comando: git status --short → OK" in text_out
    assert "README.md" in text_out
    record = traces(project)[-1]
    assert record["mode"] == "act"
    assert {e["tool"] for e in record["tool_events"]} >= {"read_file", "replace_in_file", "run_command"}


def test_act_plan_rejected_spends_only_planning_and_touches_nothing(project):
    runtime, messages = runtime_for(project)
    io_, out = console("n")

    outcome = run_act(runtime, "T-066 README", io=io_, confirm_switch=no_switch)

    assert outcome.status == "plan_rejected"
    assert len(messages.calls) == 1
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "develop"


def test_act_commit_rejected_leaves_changes_on_branch(project):
    runtime, _ = runtime_for(project)
    io_, out = console("s", "n")

    outcome = run_act(runtime, "T-066 README", io=io_, confirm_switch=no_switch)

    assert outcome.status == "not_committed"
    assert git(project, "status", "--porcelain") != ""
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == outcome.branch


def test_act_refuses_dirty_worktree_and_asks_issue_when_missing(project):
    runtime, messages = runtime_for(project)
    (project / "README.md").write_text("cambio sin commitear\n", encoding="utf-8")
    io_, out = console()
    assert run_act(runtime, "T-066 README", io=io_, confirm_switch=no_switch).status == "dirty_worktree"
    assert messages.calls == []

    git(project, "checkout", "--", "README.md")
    io_, out = console("")
    outcome = run_act(runtime, "actualizar README", io=io_, confirm_switch=no_switch)
    assert outcome.status == "missing_issue"


def test_runtime_traces_never_block_or_enter_the_commit(project):
    (project / ".gitignore").write_text("", encoding="utf-8")
    git(project, "commit", "-q", "-am", "no ignore")
    runtime, _ = runtime_for(project)
    run_plan_only(runtime, "T-066 README", io=console()[0], confirm_switch=no_switch)

    io_, out = console("s", "s")
    outcome = run_act(runtime, "T-066 README", io=io_, confirm_switch=no_switch)

    assert outcome.status == "committed"
    files = git(project, "show", "--name-only", "--format=", "HEAD")
    assert "README.md" in files and "runtime" not in files


def test_graphs_and_candidates_read_the_log(project, capsys):
    from agent_dev_kit.cli import main

    runtime, _ = runtime_for(project)
    for _ in range(3):
        run_plan_only(runtime, "T-066 README", io=console()[0], confirm_switch=no_switch)

    assert main(["graphs", str(project)]) == 0
    listed = capsys.readouterr().out
    assert listed.count("planned_only") == 3
    assert "documentation" in listed and "1.000 in / 200 out" in listed

    assert main(["candidates", str(project)]) == 0
    report = capsys.readouterr().out
    assert "Usos registrados: 3" in report
    assert "documentation ×3" in report
    assert "la planificación (Triage) representa el 100%" in report


def test_planner_missing_decisions_gets_one_repair(project):
    runtime, messages = runtime_for(project)
    incomplete = dict(PLAN, agent_decisions=[])
    original = messages.create
    state = {"planner": 0}

    def create(**kwargs):
        if kwargs.get("tool_choice", {}).get("name") == "submit_output":
            state["planner"] += 1
            if state["planner"] == 1:
                messages.calls.append(kwargs)
                return msg(tool("submit_output", incomplete, "p0"), stop="tool_use")
        return original(**kwargs)

    messages.create = create
    io_, out = console()

    run_plan_only(runtime, "T-066 README", io=io_, confirm_switch=no_switch)

    assert state["planner"] == 2
    repair_prompt = messages.calls[1]["messages"][0]["content"][0]["text"]
    assert "documentation, reviewer" in repair_prompt
    assert "doc-1 · documentation" in out.getvalue()
