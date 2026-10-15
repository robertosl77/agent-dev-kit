import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_claude_assets", ROOT / "scripts" / "build_claude_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builder_covers_every_catalog_agent():
    from agent_dev_kit.agent_catalog import AVAILABLE_AGENT_KEYS

    builder = _load_builder()
    assert set(builder.AGENT_KEYS) == set(AVAILABLE_AGENT_KEYS)


def test_committed_plugin_matches_generator(tmp_path, monkeypatch):
    builder = _load_builder()
    monkeypatch.setattr(builder, "PLUGIN_DIR", tmp_path / "plugin")
    builder.write_plugin()
    committed = ROOT / "plugins" / "agent-dev-kit"
    for generated in (tmp_path / "plugin").rglob("*"):
        if generated.is_file():
            rel = generated.relative_to(tmp_path / "plugin")
            assert (committed / rel).read_text(encoding="utf-8") == generated.read_text(
                encoding="utf-8"
            ), f"plugin desactualizado: {rel} (correr scripts/build_claude_assets.py)"
