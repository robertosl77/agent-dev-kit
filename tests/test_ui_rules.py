"""Shared-UI rules from the MisAhorros Bootstrap audit (UI-1..UI-7)."""

import importlib.util
import zipfile
from pathlib import Path

from agent_dev_kit.agents.agent_frontend import FRONTEND_BASE_INSTRUCTIONS
from agent_dev_kit.agents.agent_reviewer import REVIEWER_BASE_INSTRUCTIONS
from agent_dev_kit.agents.agent_ux_ui import UX_UI_BASE_INSTRUCTIONS

ROOT = Path(__file__).resolve().parents[1]


def test_ux_ui_carries_all_seven_rules():
    for rule in ("UI-1", "UI-2", "UI-3", "UI-4", "UI-5", "UI-6", "UI-7"):
        assert f"- {rule} " in UX_UI_BASE_INSTRUCTIONS
    assert "context.rule_sources.ui_controls" in UX_UI_BASE_INSTRUCTIONS
    assert 'href="#"' in UX_UI_BASE_INSTRUCTIONS


def test_frontend_and_reviewer_apply_the_catalog_and_semantics():
    for text in (FRONTEND_BASE_INSTRUCTIONS, REVIEWER_BASE_INSTRUCTIONS):
        assert "context.rule_sources.ui_controls" in text
        assert 'href="#"' in text and 'role="button"' in text
        assert "per-action special cases" in text
    assert "change only what was audited" in FRONTEND_BASE_INSTRUCTIONS


def test_project_specific_details_stay_out_of_the_framework():
    for text in (UX_UI_BASE_INSTRUCTIONS, FRONTEND_BASE_INSTRUCTIONS, REVIEWER_BASE_INSTRUCTIONS):
        for specific in ("Bootstrap", "MisAhorros", "576", "UI_ACTIONS", "ui-control.config"):
            assert specific not in text


def test_generated_claude_ai_skills_include_the_rules(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "build_claude_assets", ROOT / "scripts" / "build_claude_assets.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "DIST_DIR", tmp_path / "skills")
    builder.write_ai_skills()
    for name, marker in (
        ("adk-ux-ui", "UI-7 Bounded scope"),
        ("adk-frontend", "Shared UI controls"),
        ("adk-reviewer", "shared-UI rules"),
    ):
        with zipfile.ZipFile(tmp_path / "skills" / f"{name}.zip") as zf:
            assert marker in zf.read(f"{name}/SKILL.md").decode("utf-8")
