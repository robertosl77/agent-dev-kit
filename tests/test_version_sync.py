from types import SimpleNamespace
import sys

import pytest

from agent_dev_kit import version_sync as sync
from agent_dev_kit.cli import build_parser


SHA = "a" * 40
TAG = "v0.3.1"


def test_update_parser_is_read_only_by_default():
    args = build_parser().parse_args(["update", "--tag", TAG])
    assert args.command == "update"
    assert args.apply is False
    assert args.yes is False
    assert args.ssh is False


@pytest.mark.parametrize("tag", [
    "main", "develop", "v0.3.1;echo bad", "v0.3.1rc1", "../../v0.3.1", "v00.3.1",
])
def test_moving_or_unsafe_tags_rejected_before_git(monkeypatch, tag):
    def fail(*args, **kwargs):
        raise AssertionError("git must not run")

    monkeypatch.setattr(sync.subprocess, "run", fail)
    with pytest.raises(ValueError, match="stable SemVer"):
        sync._resolve_tag(tag, sync.GITHUB_HTTPS)


def test_resolves_annotated_tag_to_peeled_commit(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=(
                f"{'b'*40}\trefs/tags/{TAG}\n"
                f"{SHA}\trefs/tags/{TAG}^{{}}\n"
            ),
        )

    monkeypatch.setattr(sync.subprocess, "run", fake_run)
    assert sync._resolve_tag(TAG, sync.GITHUB_HTTPS) == SHA
    argv, kw = calls[0]
    assert argv[0:3] == ["git", "ls-remote", sync.GITHUB_HTTPS]
    assert kw["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kw["timeout"] == 40


def test_read_only_preview_pins_commit_without_installing(monkeypatch):
    class FakeDist:
        version = "0.3.0"

        def read_text(self, filename):
            return None

    monkeypatch.setattr(sync, "_installed_distribution", lambda: FakeDist())
    monkeypatch.setattr(sync, "_resolve_tag", lambda t, s: SHA)
    preview = sync.preview_update(TAG)
    assert preview.installed == "0.3.0"
    assert preview.tag == TAG
    assert preview.commit == SHA
    assert preview.requirement == (
        "agent-dev-kit @ git+https://github.com/"
        f"robertosl77/agent-dev-kit.git@{SHA}"
    )
    assert preview.is_downgrade is False


def test_editable_installs_block_apply(monkeypatch):
    preview = sync.UpdatePreview(
        installed="0.3.0", tag=TAG, commit=SHA, source=sync.GITHUB_HTTPS,
        editable=True,
    )
    monkeypatch.setattr(sync.subprocess, "run", lambda *a, **k: pytest.fail("pip ran"))
    with pytest.raises(ValueError, match="Editable"):
        sync.apply_update(preview, confirmed=True)


def test_install_requires_yes_and_rejects_downgrade(monkeypatch):
    preview = sync.UpdatePreview(
        installed="0.4.0", tag=TAG, commit=SHA, source=sync.GITHUB_HTTPS,
        editable=False,
    )
    monkeypatch.setattr(sync.subprocess, "run", lambda *a, **k: pytest.fail("pip ran"))
    with pytest.raises(ValueError, match="--yes"):
        sync.apply_update(preview)
    with pytest.raises(ValueError, match="Downgrade"):
        sync.apply_update(preview, confirmed=True)


def test_apply_uses_exact_sha_without_shell(monkeypatch):
    preview = sync.UpdatePreview(
        installed="0.3.0", tag=TAG, commit=SHA, source=sync.GITHUB_HTTPS,
        editable=False,
    )
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sync.subprocess, "run", fake_run)
    sync.apply_update(preview, confirmed=True)
    assert calls == [(
        [sys.executable, "-m", "pip", "install", "--upgrade", preview.requirement],
        {"check": False},
    )]


def test_update_rejects_untrusted_source_and_pins(monkeypatch):
    monkeypatch.setattr(sync.subprocess, "run", lambda *a, **k: pytest.fail("pip ran"))
    bad = sync.UpdatePreview("0.3.0", TAG, SHA, "https://evil.example/repo", False)
    with pytest.raises(ValueError, match="Untrusted"):
        sync.apply_update(bad, confirmed=True)
    bad2 = sync.UpdatePreview("0.3.0", TAG, "main", sync.GITHUB_HTTPS, False)
    with pytest.raises(ValueError, match="Unsafe"):
        sync.apply_update(bad2, confirmed=True)


def test_cli_check_does_not_install_or_require_project(monkeypatch, capsys):
    from agent_dev_kit import cli

    preview = sync.UpdatePreview(
        installed="0.3.0", tag=TAG, commit=SHA, source=sync.GITHUB_HTTPS,
        editable=False,
    )
    monkeypatch.setattr(sync, "preview_update", lambda *a, **k: preview)
    monkeypatch.setattr(sync, "apply_update", lambda *a, **k: pytest.fail("applied"))
    assert cli.main(["update", "--tag", TAG]) == 0
    output = capsys.readouterr().out
    assert SHA in output
    assert "no se modificó" in output


def test_cli_apply_is_blocked_without_yes(monkeypatch, capsys):
    from agent_dev_kit import cli

    preview = sync.UpdatePreview(
        installed="0.3.0", tag=TAG, commit=SHA, source=sync.GITHUB_HTTPS,
        editable=False,
    )
    monkeypatch.setattr(sync, "preview_update", lambda *a, **k: preview)
    monkeypatch.setattr(sync.subprocess, "run", lambda *a, **k: pytest.fail("pip ran"))
    assert cli.main(["update", "--tag", TAG, "--apply"]) == 1
    assert "explicit --yes" in capsys.readouterr().err


def test_cli_apply_installs_after_yes(monkeypatch, capsys):
    from agent_dev_kit import cli

    preview = sync.UpdatePreview(
        installed="0.3.0", tag=TAG, commit=SHA, source=sync.GITHUB_HTTPS,
        editable=False,
    )
    observed = []
    monkeypatch.setattr(sync, "preview_update", lambda *a, **k: preview)
    monkeypatch.setattr(
        sync, "apply_update",
        lambda item, **kwargs: observed.append((item, kwargs)),
    )
    assert cli.main(["update", "--tag", TAG, "--apply", "--yes"]) == 0
    assert observed == [(
        preview, {"confirmed": True, "allow_downgrade": False},
    )]
