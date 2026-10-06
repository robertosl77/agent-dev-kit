import json
import subprocess
import urllib.error
from types import SimpleNamespace

import pytest

from agent_dev_kit.project_config import WorkspaceConfig
from agent_dev_kit.workspace_tools import (
    READ,
    WRITE,
    Workspace,
    WorkspaceError,
    agent_access,
    safe_handler,
)


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "develop")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("# Demo\nlinea dos\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def hola():\n    return 'hola'\n", encoding="utf-8")
    (tmp_path / ".agent-dev-kit").mkdir()
    (tmp_path / ".agent-dev-kit" / "project.yaml").write_text("project: {name: x}\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_read_tools_inspect_repo_without_secrets(repo):
    ws = Workspace(repo)
    listing = ws.list_files({})
    assert "README.md" in listing and "src/app.py" in listing
    assert ".env\n" not in listing + "\n" and ".env.example" in listing
    assert "1: # Demo" in ws.read_file({"path": "README.md"})
    assert "src/app.py:1:" in ws.search({"pattern": "def hola"})
    assert "init" in ws.git_log({})
    assert [event["tool"] for event in ws.events][:3] == ["list_files", "read_file", "search"]


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", ".git/config", ".env"])
def test_reading_outside_project_git_or_secrets_is_refused(repo, path):
    with pytest.raises(WorkspaceError):
        Workspace(repo).read_file({"path": path})


def test_write_tools_change_files_but_not_agent_dev_kit_config(repo):
    ws = Workspace(repo)
    ws.replace_in_file({"path": "README.md", "old_text": "linea dos", "new_text": "línea 2"})
    ws.write_file({"path": "docs/nuevo.md", "content": "hola"})
    assert "línea 2" in (repo / "README.md").read_text(encoding="utf-8")
    assert (repo / "docs" / "nuevo.md").exists()
    with pytest.raises(WorkspaceError, match=".agent-dev-kit"):
        ws.write_file({"path": ".agent-dev-kit/project.yaml", "content": "x"})
    with pytest.raises(WorkspaceError, match="exactly once"):
        ws.replace_in_file({"path": "README.md", "old_text": "no existe", "new_text": "x"})


def test_commands_test_run_alone_allowed_ask_and_others_are_refused(repo):
    approvals = []
    ws = Workspace(
        repo,
        WorkspaceConfig(test_commands=("git status",), allowed_commands=("git log",)),
        approve_command=lambda command: approvals.append(command) or False,
    )
    assert ws.run_command({"command": "git status --short"}).startswith("exit code 0")
    assert approvals == []
    with pytest.raises(WorkspaceError, match="did not approve"):
        ws.run_command({"command": "git log -1"})
    assert approvals == ["git log -1"]
    with pytest.raises(WorkspaceError, match="not allowed"):
        ws.run_command({"command": "rm -rf ."})


def test_tool_catalog_by_access(repo):
    ws = Workspace(repo)
    read_names = {tool.name for tool in ws.tools(READ)}
    write_names = {tool.name for tool in ws.tools(WRITE)}
    assert "write_file" not in read_names and "run_command" not in read_names
    assert {"write_file", "replace_in_file", "run_command"} <= write_names
    assert agent_access("reviewer", None) == READ
    assert agent_access("backend", None) == WRITE
    assert agent_access("backend", "read_only") == READ


def test_safe_handler_returns_refusals_as_text(repo):
    tool = next(t for t in Workspace(repo).tools(READ) if t.name == "read_file")
    assert safe_handler(tool)({"path": ".env"}).startswith("Error:")


def test_read_issue_anonymous_then_token_when_private(repo, monkeypatch):
    git(repo, "remote", "add", "origin", "https://github.com/acme/demo.git")
    calls = []

    def fake_request(self, path, token):
        calls.append((path, token))
        if token is None:
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
        if path.endswith("/comments?per_page=20"):
            return [{"user": {"login": "rob"}, "body": "comentario"}]
        return {"number": 7, "state": "open", "title": "Arreglar", "body": "detalle", "comments": 1}

    monkeypatch.setattr(Workspace, "_github_request", fake_request)
    asked = []
    ws = Workspace(repo, ask_github_token=lambda reason: asked.append(reason) or "tok")

    text = ws.read_issue({"number": 7})

    assert "#7 [open] Arreglar" in text and "comentario" in text
    assert calls[0] == ("/repos/acme/demo/issues/7", None)
    assert calls[1][1] == "tok" and len(asked) == 1
