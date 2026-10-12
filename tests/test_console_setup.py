import io
from types import SimpleNamespace

import pytest

from agent_dev_kit.console_setup import ConsoleSetup, SessionCredentials, SetupCancelled
from agent_dev_kit.model_catalog import ModelOption, list_models
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.provider_registry import BUILTIN_PROVIDERS, build_default_registry


KEY_ENV_VARS = [
    name for spec in BUILTIN_PROVIDERS.values() for name in spec.env_vars
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in KEY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def project(provider="openai"):
    return ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider=provider),
        enabled_agents=("triage", "backend"),
        agents={},
    )


class Script:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def setup(inputs, secrets, models=None, lister_error=None):
    out = io.StringIO()
    seen = []

    def lister(provider, key):
        seen.append((provider, key))
        if lister_error:
            raise lister_error
        return models or []

    console = ConsoleSetup(
        input_fn=inputs,
        secret_fn=secrets,
        out=out,
        model_lister=lister,
    )
    return console, out, seen


MODELS = [
    ModelOption(id="claude-big", label="Big", tags=("línea opus",)),
    ModelOption(id="claude-small", label="Small", tags=("línea haiku",)),
]


def test_enter_selects_preferred_provider_then_asks_key_and_model():
    inputs = Script("", "2")
    secrets = Script("sk-ant-secret")
    console, out, seen = setup(inputs, secrets, MODELS)

    selection = console.run(project("anthropic"))

    assert selection.provider == "anthropic"
    assert selection.model == "claude-small"
    assert selection.config.provider.provider == "anthropic"
    assert selection.config.provider.default_model == "claude-small"
    assert seen == [("anthropic", "sk-ant-secret")]
    assert selection.credentials("anthropic") == "sk-ant-secret"
    text = out.getvalue()
    assert "(preferido)" in text
    assert "[línea opus]" in text
    assert "piensa" not in text
    assert "sk-ant-secret" not in text


def test_menu_lists_all_providers_and_allows_another_one():
    inputs = Script("2", "1")
    console, out, _ = setup(inputs, Script("gem-key"), [ModelOption("gemini-x", "x")])

    selection = console.run(project("openai"))

    assert selection.provider == "gemini"
    assert selection.model == "gemini-x"
    text = out.getvalue()
    for spec in BUILTIN_PROVIDERS.values():
        assert spec.label in text


def test_environment_key_is_used_without_asking(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    secrets = Script()
    console, out, seen = setup(Script("1"), secrets, MODELS)

    selection = console.run(project("anthropic"), provider="anthropic")

    assert secrets.prompts == []
    assert seen == [("anthropic", None)]
    assert selection.credentials("anthropic") is None
    assert "ANTHROPIC_API_KEY" in out.getvalue()


def test_model_can_be_typed_when_listing_fails():
    console, out, _ = setup(
        Script("claude-manual"),
        Script("sk-ant-key"),
        lister_error=RuntimeError("connection error"),
    )

    selection = console.run(project("anthropic"), provider="anthropic")

    assert selection.model == "claude-manual"
    assert "No se pudo obtener la lista de modelos" in out.getvalue()


def test_pasted_key_is_cleaned_of_invisible_characters():
    console, out, seen = setup(Script("1"), Script("\x16 sk-ant-ab\u00a0c\r\n"), MODELS)

    selection = console.run(project("anthropic"), provider="anthropic")

    assert seen == [("anthropic", "sk-ant-abc")]
    assert selection.credentials("anthropic") == "sk-ant-abc"
    assert "Se quitaron 3 caracteres invisibles" in out.getvalue()


def test_key_with_wrong_format_is_asked_again_with_paste_hint():
    secrets = Script("\x16", "sk-ant-good")
    console, out, seen = setup(Script("1"), secrets, MODELS)

    console.run(project("anthropic"), provider="anthropic")

    assert len(secrets.prompts) == 2
    assert seen == [("anthropic", "sk-ant-good")]
    text = out.getvalue()
    assert "clic derecho" in text
    assert "good" not in text


def test_rejected_key_while_listing_can_be_pasted_again():
    import httpx
    anthropic = pytest.importorskip("anthropic")
    response = httpx.Response(
        400,
        request=httpx.Request("GET", "https://api.anthropic.com/v1/models"),
        text="Bad Request: header inválido",
    )
    calls = []

    def lister(provider, key):
        calls.append(key)
        if len(calls) == 1:
            raise anthropic.BadRequestError("Error code: 400", response=response, body=None)
        return MODELS

    out = io.StringIO()
    console = ConsoleSetup(
        input_fn=Script("s", "1"),
        secret_fn=Script("sk-ant-bad", "sk-ant-good"),
        out=out,
        model_lister=lister,
    )

    selection = console.run(project("anthropic"), provider="anthropic")

    assert calls == ["sk-ant-bad", "sk-ant-good"]
    assert selection.model == "claude-big"
    assert selection.credentials("anthropic") == "sk-ant-good"
    text = out.getvalue()
    assert "respuesta: Bad Request: header inválido" in text
    assert "mal pegada" in text


def test_flags_skip_menus():
    inputs = Script()
    console, _, seen = setup(inputs, Script("key"))

    selection = console.run(project(), provider="gemini", model="gemini-flash")

    assert (selection.provider, selection.model) == ("gemini", "gemini-flash")
    assert inputs.prompts == []
    assert seen == []


def test_no_preferred_model_is_ever_preselected():
    console, _, _ = setup(Script("", "", ""), Script("sk-ant-key"), MODELS)

    with pytest.raises(SetupCancelled):
        console.run(project("anthropic"), provider="anthropic")


def test_empty_key_is_rejected_after_three_attempts():
    console, _, _ = setup(Script(), Script("", "", ""))

    with pytest.raises(SetupCancelled):
        console.run(project("anthropic"), provider="anthropic")


def test_options_of_preferred_provider_are_not_sent_to_another_provider():
    config = project("openai")
    config = config.__class__(
        **{
            **{f: getattr(config, f) for f in config.__dataclass_fields__},
            "provider": ProviderConfig(provider="openai", options={"base_url": "x"}),
        }
    )
    console, _, _ = setup(Script(), Script("sk-ant-key"))

    selection = console.run(config, provider="anthropic", model="m")

    assert selection.config.provider.options == {}


def test_credentials_never_show_keys_and_ask_lazily_for_fallbacks():
    asked = []
    credentials = SessionCredentials(ask=lambda provider: asked.append(provider) or "k2")
    credentials.set("anthropic", "k1")

    assert credentials("anthropic") == "k1"
    assert credentials("gemini") == "k2"
    assert credentials("gemini") == "k2"
    assert asked == ["gemini"]
    assert "k1" not in repr(credentials) and "k2" not in repr(credentials)


def test_default_registry_passes_runtime_key_to_provider():
    registry = build_default_registry({"anthropic": "runtime-key"})
    provider = registry.create(
        ProviderConfig(provider="anthropic", default_model="claude-test")
    )

    assert provider.api_key == "runtime-key"
    assert provider.default_model == "claude-test"
    assert set(registry.keys()) == {"anthropic", "gemini", "openai"}


def test_anthropic_listing_shows_line_but_not_thinking_newest_first():
    rows = [
        SimpleNamespace(
            id="old",
            display_name="Old",
            created_at="2025-01-01",
            capabilities=None,
            model_extra={},
        ),
        SimpleNamespace(
            id="new",
            display_name="New",
            created_at="2026-07-01",
            capabilities=SimpleNamespace(thinking=SimpleNamespace(supported=True)),
            line="opus",
        ),
    ]
    client = SimpleNamespace(models=SimpleNamespace(list=lambda limit: rows))

    options = list_models("anthropic", "k", client=client)

    assert [item.id for item in options] == ["new", "old"]
    assert options[0].tags == ("línea opus",)
    assert options[1].tags == ()


def test_gemini_listing_keeps_only_text_generation_models():
    rows = [
        SimpleNamespace(
            name="models/gemini-flash",
            display_name="Flash",
            supported_actions=["generateContent"],
            thinking=True,
        ),
        SimpleNamespace(
            name="models/gemini-embedding",
            display_name="Embedding",
            supported_actions=["embedContent"],
            thinking=False,
        ),
    ]
    client = SimpleNamespace(models=SimpleNamespace(list=lambda: rows))

    options = list_models("gemini", "k", client=client)

    assert [(item.id, item.tags) for item in options] == [("gemini-flash", ())]


def test_openai_listing_filters_chat_models_without_guessing_tags():
    rows = [
        SimpleNamespace(id="gpt-new", created=200),
        SimpleNamespace(id="text-embedding-3", created=300),
        SimpleNamespace(id="gpt-old", created=100),
    ]
    client = SimpleNamespace(models=SimpleNamespace(list=lambda: rows))

    options = list_models("openai", "k", client=client)

    assert [item.id for item in options] == ["gpt-new", "gpt-old"]
    assert all(item.tags == () for item in options)
