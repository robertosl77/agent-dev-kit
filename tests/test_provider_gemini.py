from types import SimpleNamespace

import pytest

genai_types = pytest.importorskip("google.genai.types")
genai_errors = pytest.importorskip("google.genai.errors")

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.planner_contract import StructuredTaskPlan
from agent_dev_kit.provider_errors import (
    ProviderAuthenticationError,
    ProviderQuotaExceeded,
)
from agent_dev_kit.providers.provider_gemini import GeminiProvider


def response(*parts, finish="STOP"):
    content = genai_types.Content(role="model", parts=list(parts))
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=content, finish_reason=finish)]
    )


def text(value):
    return genai_types.Part(text=value)


def call(name, args=None, call_id="c1"):
    return genai_types.Part(
        function_call=genai_types.FunctionCall(id=call_id, name=name, args=args or {})
    )


class FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


def provider_with(responses):
    client = FakeClient(responses)
    return GeminiProvider(default_model="gemini-test", client=client), client.models


def definition(name, instructions="Instructions."):
    return AgentDefinition(name=name, instructions=instructions)


def test_text_answer_and_disabled_automatic_function_calling():
    provider, models = provider_with([response(text("Hola"))])
    agent = provider.create_agent(definition("Agent Backend", "Backend rules."))

    result = provider.run_sync(agent, "hola")

    assert result.output == "Hola"
    request = models.calls[0]
    assert request["model"] == "gemini-test"
    assert request["config"].system_instruction == "Backend rules."
    assert request["config"].automatic_function_calling.disable is True
    assert request["config"].tools is None


def test_handoff_keeps_native_model_content_and_switches_agent():
    provider, models = provider_with(
        [response(call("transfer_to_agent_backend")), response(text("Soy Backend"))]
    )
    backend = provider.create_agent(definition("Agent Backend", "Backend rules."))
    triage = provider.create_agent(definition("Agent Triage"))
    provider.set_handoffs(triage, (backend,))

    result = provider.run_sync(triage, "arreglá el endpoint")

    assert result.output == "Soy Backend"
    assert result.active_agent is backend
    second = models.calls[1]
    contents = second["contents"]
    assert contents[1].role == "model"
    assert contents[1].parts[0].function_call.name == "transfer_to_agent_backend"
    assert contents[2].parts[0].function_response.id == "c1"
    assert second["config"].system_instruction == "Backend rules."


def test_structured_output_uses_forced_function_call():
    provider, models = provider_with([response(call("submit_output", {"request": "x"}))])
    planner = provider.create_structured_agent(
        definition("Agent Triage Planner"),
        output_type=StructuredTaskPlan,
    )

    result = provider.run_sync(planner, "plan")

    assert result.output == {"request": "x"}
    config = models.calls[0]["config"]
    calling = config.tool_config.function_calling_config
    assert str(calling.mode).endswith("ANY")
    assert calling.allowed_function_names == ["submit_output"]
    declaration = config.tools[0].function_declarations[0]
    assert declaration.parameters_json_schema["type"] == "object"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            genai_errors.ClientError(
                429,
                {
                    "error": {
                        "code": 429,
                        "message": "You exceeded your current quota.",
                        "status": "RESOURCE_EXHAUSTED",
                    }
                },
            ),
            ProviderQuotaExceeded,
        ),
        (
            genai_errors.ClientError(
                400,
                {
                    "error": {
                        "code": 400,
                        "message": "API key not valid. Please pass a valid API key.",
                        "status": "INVALID_ARGUMENT",
                    }
                },
            ),
            ProviderAuthenticationError,
        ),
    ],
)
def test_gemini_errors_are_normalized(error, expected):
    provider, _ = provider_with([error])
    agent = provider.create_agent(definition("Agent Backend"))

    with pytest.raises(expected):
        provider.run_sync(agent, "hola")


def test_missing_key_is_reported_before_any_call(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiProvider(default_model="gemini-test")
