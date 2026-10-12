"""Local Git operations for action mode (M-076), always through the policy.

Only two mutations exist, and both go through GitMutationGateway, so
GitPolicyGuard validates them before git runs:

    create_task_branch → git checkout -b <task branch> <develop>
    direct_write       → git add -A && git commit   (only on the task branch)

Nothing is pushed. Push and PR are done by the person, on explicit order.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from agent_dev_kit.git_mutation import GitMutationGateway
from agent_dev_kit.git_policy import GitPolicyGuard, GitWorkflowConfig
from agent_dev_kit.workspace_tools import run_git


RUNTIME_DIR = ".agent-dev-kit/runtime"


class GitActionError(RuntimeError):
    pass


class LocalRepositoryVerifier:
    """Checks the real local repository instead of trusting the caller (M-063)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.reason = ""

    def branch_exists(self, branch: str) -> bool:
        return run_git(
            self.root, ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"]
        ).returncode == 0

    def is_up_to_date(self, branch: str) -> bool:
        if run_git(self.root, ["remote", "get-url", "origin"]).returncode != 0:
            self.reason = "sin remoto origin: se usa la rama local"
            return True
        fetched = run_git(self.root, ["fetch", "--quiet", "origin", branch])
        if fetched.returncode != 0:
            self.reason = f"no se pudo actualizar origin/{branch}: {fetched.stderr.strip()}"
            return False
        local = run_git(self.root, ["rev-parse", branch]).stdout.strip()
        remote = run_git(self.root, ["rev-parse", f"origin/{branch}"]).stdout.strip()
        if local != remote:
            self.reason = (
                f"'{branch}' local no coincide con origin/{branch}: "
                f"actualizalo con git checkout {branch} && git pull"
            )
            return False
        return True


class LocalGitExecutor:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def __call__(self, operation: str, arguments: Mapping[str, Any]) -> str:
        if operation == "create_task_branch":
            result = run_git(
                self.root,
                ["checkout", "-b", arguments["branch"], arguments["base_branch"]],
            )
        elif operation == "direct_write":
            message = str(arguments["payload"].get("message") or "agent-dev-kit")
            # Runtime traces are local evidence, never part of the commit.
            added = run_git(self.root, ["add", "-A"])
            if added.returncode != 0:
                raise GitActionError(added.stderr.strip())
            run_git(self.root, ["reset", "-q", "--", RUNTIME_DIR])
            result = run_git(self.root, ["commit", "-m", message])
        else:
            raise GitActionError(f"Unsupported local git operation '{operation}'.")
        if result.returncode != 0:
            raise GitActionError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()


def local_gateway(root: Path, workflow: GitWorkflowConfig) -> GitMutationGateway:
    return GitMutationGateway(
        GitPolicyGuard(workflow),
        LocalGitExecutor(root),
        verifier=LocalRepositoryVerifier(root),
    )


def current_branch(root: Path) -> str:
    return run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def is_git_repository(root: Path) -> bool:
    return run_git(root, ["rev-parse", "--is-inside-work-tree"]).returncode == 0


def uncommitted_changes(root: Path) -> list[str]:
    output = run_git(root, ["status", "--porcelain", "--untracked-files=all"]).stdout
    return [
        line
        for line in output.splitlines()
        if line.strip() and not line[3:].startswith(RUNTIME_DIR)
    ]


def diff_stat(root: Path) -> str:
    """Changed tracked files (with +/-) and new files, without touching the index."""

    tracked = run_git(root, ["diff", "--stat"]).stdout.strip()
    new_files = [
        line[3:]
        for line in uncommitted_changes(root)
        if line.startswith("??")
    ]
    parts = [tracked] if tracked else []
    parts += [f" {name} (nuevo)" for name in new_files]
    return "\n".join(parts)


_ISSUE_PATTERNS = (
    re.compile(r"\b([A-Z]{1,3}-\d{1,5})\b"),
    re.compile(r"#(\d+)\b"),
)


def issue_reference(request: str) -> str | None:
    for pattern in _ISSUE_PATTERNS:
        match = pattern.search(request)
        if match:
            return match.group(1)
    return None


def branch_kind(request: str) -> str:
    lowered = request.lower()
    if re.search(r"\b(fix|bug|corregir|arreglar|error)\b", lowered):
        return "fix"
    if re.search(r"\b(readme|docs?|documentaci[oó]n|documentar)\b", lowered):
        return "docs"
    return "feat"


def branch_slug(request: str, issue: str | None) -> str:
    text = request
    if issue:
        text = text.replace(issue, " ").replace(f"#{issue}", " ")
    # Other issue references (e.g. "(#117)") are not part of the slug.
    text = re.sub(r"#\d+|\b[A-Z]{1,3}-\d{1,5}\b", " ", text)
    # "sección" → "seccion": drop accents instead of breaking the word.
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    stop = {"el", "la", "los", "las", "de", "del", "en", "y", "a", "un", "una",
            "the", "to", "of", "and", "issue", "resolver", "para", "con", "que"}
    meaningful = [word for word in words if word not in stop][:5]
    return "-".join(meaningful) or "tarea"
