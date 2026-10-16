import importlib.util
import json
import zipfile
from pathlib import Path

from agent_dev_kit.commands import (
    COMMAND_NAMES,
    COMMANDS,
    parse_command,
    render_help,
    render_skill_section,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ("/input", "/plan", "/grafo", "/backlog", "/do", "/testing", "/help")


def test_catalog_has_exactly_the_agreed_commands():
    assert COMMAND_NAMES == EXPECTED
    assert "/task" not in COMMAND_NAMES


def test_parse_first_word_only_and_one_command_per_message():
    assert parse_command("hola /do") == parse_command("hola /do")
    assert parse_command("hola /do").name is None
    parsed = parse_command("/input /do esto es texto")
    assert parsed.name == "/input" and parsed.argument == "/do esto es texto"
    assert parse_command("/PLAN agregá X").name == "/plan"
    assert parse_command("/plan\nlínea 2").argument == "línea 2"
    unknown = parse_command("/plna algo")
    assert unknown.unknown and unknown.name == "/plna"


def test_help_and_skill_list_every_command():
    help_text = render_help()
    skill = render_skill_section()
    for command in COMMANDS:
        assert command.usage in help_text
        assert f"`{command.usage}`" in skill
        assert f"### `{command.name}`" in skill
    assert "/plan [texto]" in help_text
    assert "Leído" in skill and "RF" in skill and "RNF" in skill


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_claude_assets", ROOT / "scripts" / "build_claude_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_claude_ai_triage_skill_carries_the_commands(tmp_path, monkeypatch):
    builder = _builder()
    monkeypatch.setattr(builder, "DIST_DIR", tmp_path / "skills")
    builder.write_ai_skills()
    with zipfile.ZipFile(tmp_path / "skills" / "adk-triage.zip") as zf:
        skill = zf.read("adk-triage/SKILL.md").decode("utf-8")
    assert render_skill_section() in skill
    assert '"backlog"' in skill and '"agreed"' in skill
    # The specialists do not get the command section: only the orchestrator.
    with zipfile.ZipFile(tmp_path / "skills" / "adk-backend.zip") as zf:
        assert "## Commands" not in zf.read("adk-backend/SKILL.md").decode("utf-8")
