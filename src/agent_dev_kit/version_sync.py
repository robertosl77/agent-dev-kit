"""Explicit, pinned GitHub release updates; no background self-update.

Updates are never fetched from a moving branch. The exact tagged commit is
resolved before pip is invoked. Credentials belong to Git's credential helper.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable


GITHUB_HTTPS = "https://github.com/robertosl77/agent-dev-kit.git"
GITHUB_SSH = "ssh://git@github.com/robertosl77/agent-dev-kit.git"
STABLE_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class UpdatePreview:
    installed: str
    tag: str
    commit: str
    source: str
    editable: bool

    @property
    def requirement(self) -> str:
        return f"agent-dev-kit @ git+{self.source}@{self.commit}"

    @property
    def is_downgrade(self) -> bool:
        current = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", self.installed)
        target = STABLE_TAG.fullmatch(self.tag)
        return bool(current and target and tuple(map(int, target.groups())) < tuple(map(int, current.groups())))


def _installed_distribution() -> metadata.Distribution:
    try:
        return metadata.distribution("agent-dev-kit")
    except metadata.PackageNotFoundError as exc:
        raise ValueError("Agent Dev Kit is not installed in this Python environment.") from exc


def _is_editable(dist: metadata.Distribution) -> bool:
    raw = dist.read_text("direct_url.json")
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return False
    return bool((data.get("dir_info") or {}).get("editable"))


def _resolve_tag(tag: str, source: str) -> str:
    if STABLE_TAG.fullmatch(tag) is None:
        raise ValueError("Only exact stable SemVer tags (e.g. v0.3.1) are accepted.")
    cmd = [
        "git", "ls-remote", source,
        f"refs/tags/{tag}^{{}}", f"refs/tags/{tag}",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=40,
            check=False, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("GitHub release verification failed.") from exc
    if result.returncode != 0:
        raise RuntimeError(
            "Cannot read exact GitHub tag. Verify repository access and Git credentials."
        )
    tags: dict[str, str] = {}
    for row in result.stdout.splitlines():
        sha, sep, ref = row.partition("\t")
        if sep and COMMIT_SHA.fullmatch(sha):
            tags[ref] = sha
    sha = tags.get(f"refs/tags/{tag}^{{}}") or tags.get(f"refs/tags/{tag}")
    if sha is None:
        raise ValueError(f"Tag {tag} was not found on the configured GitHub repository.")
    return sha


def preview_update(tag: str, *, use_ssh: bool = False) -> UpdatePreview:
    dist = _installed_distribution()
    source = GITHUB_SSH if use_ssh else GITHUB_HTTPS
    sha = _resolve_tag(tag, source)
    return UpdatePreview(
        installed=dist.version, tag=tag, commit=sha,
        source=source, editable=_is_editable(dist),
    )


def apply_update(
    preview: UpdatePreview,
    *,
    confirmed: bool = False,
    allow_downgrade: bool = False,
) -> None:
    """Install exact verified commit, after affirmative host authorization."""
    if not confirmed:
        raise ValueError("Installation requires explicit --yes confirmation.")
    if preview.editable:
        raise ValueError(
            "Editable development install detected. Update its Git checkout "
            "manually; do not replace it with a packaged version."
        )
    if preview.is_downgrade and not allow_downgrade:
        raise ValueError("Downgrade blocked. Use --allow-downgrade deliberately.")
    if preview.source not in {GITHUB_HTTPS, GITHUB_SSH}:
        raise ValueError("Untrusted update source.")
    if not COMMIT_SHA.fullmatch(preview.commit) or STABLE_TAG.fullmatch(preview.tag) is None:
        raise ValueError("Unsafe or unverified update pin.")
    # No shell, injected flags, moving tag or optional project path.
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", preview.requirement],
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Pinned update failed (pip exit code {result.returncode}).")
