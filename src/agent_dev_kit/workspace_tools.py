"""Built-in tools so agents can inspect and change the consuming project (M-076).

Two access levels:

    read  (consultant): list_files, read_file, search, git_status, git_log,
                        git_diff, read_issue
    write (action /do): + write_file, replace_in_file, run_command

Safety rules applied here, independent of the model:

- every path is resolved inside the project root; ``..`` and absolute paths
  outside it are rejected;
- ``.git/`` is never read or written; ``.agent-dev-kit/`` is never written;
- secret files (``.env``, ``.env.*`` except ``.env.example``) are never read
  or written;
- ``run_command`` only runs commands declared in ``project.yaml``
  (``workspace.test_commands`` run without asking; ``allowed_commands`` ask
  the person first); anything else is rejected;
- git is read-only here. Branch and commit go through GitMutationGateway.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from agent_dev_kit.project_config import WorkspaceConfig


READ = "read"
WRITE = "write"

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".angular",
}

# Agents that may change files in action mode unless the project overrides
# it with ``access:`` in .agent-dev-kit/agents/<agent>.yaml.
DEFAULT_READ_WRITE_AGENTS = {
    "backend",
    "frontend",
    "database",
    "testing",
    "documentation",
    "devops",
    "ux_ui",
    "data",
    "performance",
    "observability",
    "security",
}


class WorkspaceError(ValueError):
    """A tool request the workspace refuses. The model receives the message."""


@dataclass(frozen=True, slots=True)
class BuiltinTool:
    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    access: str = READ


ApproveFn = Callable[[str], bool]
SecretFn = Callable[[str], "str | None"]


@dataclass(slots=True)
class Workspace:
    root: Path
    config: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    approve_command: ApproveFn | None = None
    ask_github_token: SecretFn | None = None
    github_api: str = "https://api.github.com"
    events: list[dict[str, Any]] = field(default_factory=list)
    _github_token: str | None = field(default=None, repr=False)
    _trace: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()

    # ----------------------------------------------------------- bookkeeping

    def bind_trace(self, trace: Any) -> None:
        """Tool events of the next run are appended to this trace."""

        self._trace = trace

    def _event(self, tool: str, ok: bool, **details: Any) -> None:
        event = {"tool": tool, "ok": ok, **details}
        self.events.append(event)
        if self._trace is not None and hasattr(self._trace, "tool_events"):
            self._trace.tool_events.append(event)

    # ----------------------------------------------------------------- paths

    def resolve(self, path: str | None, *, for_write: bool = False) -> Path:
        raw = (path or ".").strip() or "."
        candidate = (self.root / raw).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise WorkspaceError(f"Path '{raw}' is outside the project.")
        relative = candidate.relative_to(self.root)
        parts = relative.parts
        if parts and parts[0] == ".git":
            raise WorkspaceError("The .git directory is not accessible.")
        if for_write and parts and parts[0] == ".agent-dev-kit":
            raise WorkspaceError("Agents cannot modify .agent-dev-kit/.")
        if _is_secret(candidate.name):
            raise WorkspaceError(f"'{raw}' may contain secrets and is not accessible.")
        return candidate

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix() or "."

    # ------------------------------------------------------------ read tools

    def list_files(self, args: dict[str, Any]) -> str:
        base = self.resolve(args.get("path"))
        pattern = str(args.get("pattern") or "*")
        limit = 300
        found: list[str] = []
        for current, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if _is_secret(name) or not fnmatch.fnmatch(name, pattern):
                    continue
                found.append(self.rel(Path(current) / name))
                if len(found) >= limit:
                    break
            if len(found) >= limit:
                break
        self._event("list_files", True, path=self.rel(base), results=len(found))
        suffix = f"\n... (truncated at {limit})" if len(found) >= limit else ""
        return "\n".join(found) + suffix if found else "(no files)"

    def read_file(self, args: dict[str, Any]) -> str:
        path = self.resolve(args.get("path"))
        if not path.is_file():
            raise WorkspaceError(f"'{args.get('path')}' is not a file.")
        start = max(int(args.get("start_line") or 1), 1)
        max_lines = max(min(int(args.get("max_lines") or 400), 2000), 1)
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        selected = lines[start - 1 : start - 1 + max_lines]
        numbered = "\n".join(
            f"{number}: {line}"
            for number, line in enumerate(selected, start=start)
        )
        limit = self.config.max_read_bytes
        truncated = len(numbered.encode("utf-8")) > limit
        if truncated:
            numbered = numbered.encode("utf-8")[:limit].decode("utf-8", "ignore")
        self._event("read_file", True, path=self.rel(path))
        note = ""
        end = start - 1 + len(selected)
        if truncated or end < len(lines):
            note = (
                f"\n... (showing lines {start}-{end} of {len(lines)}; "
                "use start_line to read more)"
            )
        return numbered + note

    def search(self, args: dict[str, Any]) -> str:
        pattern = str(args.get("pattern") or "")
        if not pattern:
            raise WorkspaceError("pattern is required.")
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise WorkspaceError(f"Invalid regular expression: {exc}") from exc
        base = self.resolve(args.get("path"))
        glob = str(args.get("glob") or "*")
        limit = self.config.max_search_results
        results: list[str] = []
        for current, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if _is_secret(name) or not fnmatch.fnmatch(name, glob):
                    continue
                file_path = Path(current) / name
                try:
                    with file_path.open("r", encoding="utf-8") as stream:
                        for number, line in enumerate(stream, start=1):
                            if regex.search(line):
                                results.append(
                                    f"{self.rel(file_path)}:{number}: {line.strip()[:200]}"
                                )
                                if len(results) >= limit:
                                    break
                except (UnicodeDecodeError, OSError):
                    continue
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        self._event("search", True, pattern=pattern[:80], results=len(results))
        if not results:
            return "(no matches)"
        suffix = f"\n... (truncated at {limit} matches)" if len(results) >= limit else ""
        return "\n".join(results) + suffix

    def git_status(self, args: dict[str, Any]) -> str:
        return self._git_read("git_status", ["status", "--short", "--branch"])

    def git_log(self, args: dict[str, Any]) -> str:
        count = max(min(int(args.get("count") or 15), 100), 1)
        command = ["log", f"-{count}", "--oneline", "--decorate"]
        if args.get("path"):
            command += ["--", self.rel(self.resolve(args.get("path")))]
        return self._git_read("git_log", command)

    def git_diff(self, args: dict[str, Any]) -> str:
        command = ["diff"]
        if args.get("staged"):
            command.append("--staged")
        if args.get("path"):
            command += ["--", self.rel(self.resolve(args.get("path")))]
        output = self._git_read("git_diff", command)
        limit = self.config.max_read_bytes
        if len(output) > limit:
            output = output[:limit] + "\n... (diff truncated)"
        return output or "(no changes)"

    def _git_read(self, tool: str, arguments: list[str]) -> str:
        completed = run_git(self.root, arguments)
        ok = completed.returncode == 0
        self._event(tool, ok)
        if not ok:
            raise WorkspaceError(completed.stderr.strip() or f"git {arguments[0]} failed.")
        return completed.stdout.strip()

    def read_issue(self, args: dict[str, Any]) -> str:
        number = int(str(args.get("number") or "0").lstrip("#") or 0)
        if number <= 0:
            raise WorkspaceError("number must be a GitHub issue number.")
        owner, repo = self.github_repository()
        issue = self._github_get(f"/repos/{owner}/{repo}/issues/{number}")
        comments: list[Any] = []
        if int(issue.get("comments") or 0):
            comments = self._github_get(
                f"/repos/{owner}/{repo}/issues/{number}/comments?per_page=20"
            )
        self._event("read_issue", True, issue=number)
        lines = [
            f"#{issue.get('number')} [{issue.get('state')}] {issue.get('title')}",
            "",
            str(issue.get("body") or "(no description)"),
        ]
        for comment in comments:
            author = (comment.get("user") or {}).get("login", "?")
            lines += ["", f"--- comment by {author}:", str(comment.get("body") or "")]
        text = "\n".join(lines)
        limit = self.config.max_read_bytes
        return text if len(text) <= limit else text[:limit] + "\n... (truncated)"

    def github_repository(self) -> tuple[str, str]:
        completed = run_git(self.root, ["remote", "get-url", "origin"])
        url = completed.stdout.strip()
        match = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?/?$", url)
        if completed.returncode != 0 or not match:
            raise WorkspaceError(
                "The project has no GitHub 'origin' remote, so issues cannot be read."
            )
        return match.group(1), match.group(2)

    def _github_get(self, path: str) -> Any:
        # Decision 3C: anonymous for public repositories; a read-only token is
        # asked only for private repositories or when the anonymous quota runs
        # out. The token stays in memory.
        try:
            return self._github_request(path, self._github_token)
        except urllib.error.HTTPError as exc:
            needs_token = exc.code in {401, 403, 404, 429}
            if not needs_token or self._github_token or self.ask_github_token is None:
                raise WorkspaceError(_github_error(exc)) from exc
            token = self.ask_github_token(
                "GitHub pide autenticación (repo privado o límite de consultas)."
            )
            if not token:
                raise WorkspaceError(_github_error(exc)) from exc
            self._github_token = token
            try:
                return self._github_request(path, token)
            except urllib.error.HTTPError as retry:
                raise WorkspaceError(_github_error(retry)) from retry
        except urllib.error.URLError as exc:
            raise WorkspaceError(f"GitHub is not reachable: {exc.reason}") from exc

    def _github_request(self, path: str, token: str | None) -> Any:
        request = urllib.request.Request(
            self.github_api.rstrip("/") + path,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "agent-dev-kit",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    # ----------------------------------------------------------- write tools

    def write_file(self, args: dict[str, Any]) -> str:
        path = self.resolve(args.get("path"), for_write=True)
        content = str(args.get("content") or "")
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._event("write_file", True, path=self.rel(path), created=not existed)
        return f"{'Updated' if existed else 'Created'} {self.rel(path)} ({len(content)} chars)."

    def replace_in_file(self, args: dict[str, Any]) -> str:
        path = self.resolve(args.get("path"), for_write=True)
        if not path.is_file():
            raise WorkspaceError(f"'{args.get('path')}' is not a file.")
        old = str(args.get("old_text") or "")
        new = str(args.get("new_text") or "")
        if not old:
            raise WorkspaceError("old_text is required.")
        text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count != 1:
            raise WorkspaceError(
                f"old_text must appear exactly once in {self.rel(path)} (found {count}). "
                "Read the file and include more surrounding lines."
            )
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        self._event("replace_in_file", True, path=self.rel(path))
        return f"Updated {self.rel(path)}."

    def run_command(self, args: dict[str, Any]) -> str:
        command = " ".join(str(args.get("command") or "").split())
        if not command:
            raise WorkspaceError("command is required.")
        cwd = self.resolve(args.get("cwd"))
        kind = self.command_kind(command)
        if kind is None:
            allowed = list(self.config.test_commands) + list(self.config.allowed_commands)
            self._event("run_command", False, command=command, reason="not_allowed")
            raise WorkspaceError(
                "Command not allowed by the project. Allowed: "
                + (", ".join(allowed) if allowed else "none (declare them in workspace.test_commands)")
            )
        if kind == "ask":
            approved = bool(self.approve_command and self.approve_command(command))
            if not approved:
                self._event("run_command", False, command=command, reason="rejected")
                raise WorkspaceError(f"The person did not approve running: {command}")
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            self._event("run_command", False, command=command, reason="timeout")
            raise WorkspaceError(f"Command timed out: {command}") from exc
        output = (completed.stdout or "") + (completed.stderr or "")
        self._event(
            "run_command",
            completed.returncode == 0,
            command=command,
            exit_code=completed.returncode,
        )
        tail = output[-4000:]
        return f"exit code {completed.returncode}\n{tail}".strip()

    def command_kind(self, command: str) -> str | None:
        normalized = " ".join(command.split())
        for allowed in self.config.test_commands:
            if _command_matches(normalized, allowed):
                return "auto"
        for allowed in self.config.allowed_commands:
            if _command_matches(normalized, allowed):
                return "ask"
        return None

    # ------------------------------------------------------------- catalog

    def tools(self, access: str) -> list[BuiltinTool]:
        path_param = {"type": "string", "description": "Path relative to the project root."}
        read_tools = [
            BuiltinTool(
                "list_files",
                "List project files (skips .git, node_modules, virtualenvs and secrets).",
                _schema({"path": path_param, "pattern": {"type": "string", "description": "Glob for file names, e.g. *.py"}}),
                self.list_files,
            ),
            BuiltinTool(
                "read_file",
                "Read a text file with line numbers. Use start_line/max_lines for long files.",
                _schema(
                    {
                        "path": path_param,
                        "start_line": {"type": "integer"},
                        "max_lines": {"type": "integer"},
                    },
                    required=["path"],
                ),
                self.read_file,
            ),
            BuiltinTool(
                "search",
                "Search a regular expression in project files. Returns file:line: text.",
                _schema(
                    {
                        "pattern": {"type": "string"},
                        "path": path_param,
                        "glob": {"type": "string", "description": "Glob for file names, e.g. *.ts"},
                    },
                    required=["pattern"],
                ),
                self.search,
            ),
            BuiltinTool("git_status", "Show the current branch and changed files.", _schema({}), self.git_status),
            BuiltinTool(
                "git_log",
                "Show recent commits, optionally for one path.",
                _schema({"count": {"type": "integer"}, "path": path_param}),
                self.git_log,
            ),
            BuiltinTool(
                "git_diff",
                "Show uncommitted changes, optionally for one path.",
                _schema({"path": path_param, "staged": {"type": "boolean"}}),
                self.git_diff,
            ),
            BuiltinTool(
                "read_issue",
                "Read a GitHub issue of this project (title, body and comments).",
                _schema({"number": {"type": "integer"}}, required=["number"]),
                self.read_issue,
            ),
        ]
        if access != WRITE:
            return read_tools

        write_tools = [
            BuiltinTool(
                "write_file",
                "Create or overwrite a text file with the full content.",
                _schema(
                    {"path": path_param, "content": {"type": "string"}},
                    required=["path", "content"],
                ),
                self.write_file,
                WRITE,
            ),
            BuiltinTool(
                "replace_in_file",
                "Replace one exact fragment of a file (old_text must appear once).",
                _schema(
                    {
                        "path": path_param,
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    required=["path", "old_text", "new_text"],
                ),
                self.replace_in_file,
                WRITE,
            ),
            BuiltinTool(
                "run_command",
                "Run a command allowed by the project (tests, linters). Others are rejected.",
                _schema(
                    {
                        "command": {"type": "string"},
                        "cwd": {"type": "string", "description": "Working directory relative to the project root."},
                    },
                    required=["command"],
                ),
                self.run_command,
                WRITE,
            ),
        ]
        return read_tools + write_tools


def agent_access(agent_key: str, configured: str | None) -> str:
    if configured == "read_only":
        return READ
    if configured == "read_write":
        return WRITE
    return WRITE if agent_key in DEFAULT_READ_WRITE_AGENTS else READ


def run_git(root: Path, arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
    )


def safe_handler(tool: BuiltinTool) -> Callable[[dict[str, Any]], str]:
    """Wrap a tool so refusals and errors reach the model as text."""

    def call(args: dict[str, Any]) -> str:
        try:
            result = tool.handler(dict(args or {}))
        except WorkspaceError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # unexpected: report without crashing the run
            return f"Error running {tool.name}: {exc}"
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    return call


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _is_secret(name: str) -> bool:
    lowered = name.lower()
    if lowered == ".env.example":
        return False
    return lowered == ".env" or lowered.startswith(".env.")


def _command_matches(command: str, allowed: str) -> bool:
    allowed = " ".join(allowed.split())
    return command == allowed or command.startswith(allowed + " ")


def _github_error(exc: urllib.error.HTTPError) -> str:
    if exc.code == 404:
        return "GitHub issue not found (or the repository is private)."
    if exc.code in {401, 403, 429}:
        return "GitHub denied access (private repository, invalid token or rate limit)."
    return f"GitHub error {exc.code}."


MODE_NOTES = {
    "propose": (
        "You can inspect the current project with read-only tools (list_files, "
        "read_file, search, git_status, git_log, git_diff, read_issue). Inspect "
        "the relevant files before proposing; never invent file contents, "
        "structure or repository state. Do not modify anything."
    ),
    "act": (
        "You are working on a local task branch of the project. First inspect "
        "with the read tools, then apply your part of the change directly with "
        "write_file or replace_in_file, and run the project's test commands with "
        "run_command when relevant. Do not commit, push or switch branches: the "
        "person reviews the diff and commits. If you only have read-only tools, "
        "review the current changes (git_diff) and report findings."
    ),
}


def builtin_tools_factory(
    provider: Any,
    workspace: Workspace,
    config: Any,
    mode: str,
) -> Callable[[str], tuple[Any, ...]]:
    """Per-agent tool handles for DevAgentKit.build (M-076)."""

    from agent_dev_kit.tooling import ToolHandle

    def handles(agent_key: str) -> tuple[Any, ...]:
        if mode == "act":
            contextual = config.agent(agent_key)
            access = agent_access(agent_key, contextual.access if contextual else None)
        else:
            access = READ
        return tuple(
            ToolHandle(
                provider=provider.key,
                key=tool.name,
                native=provider.native_tool(tool),
                effect="read_only" if tool.access == READ else "workspace_write",
                enforced_policy="workspace_sandbox",
            )
            for tool in workspace.tools(access)
        )

    return handles
