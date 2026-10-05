from types import SimpleNamespace

import httpx
import pytest

anthropic = pytest.importorskip("anthropic")

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.planner_contract import StructuredTaskPlan
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.provider_errors import (
    ProviderAuthenticationError,
    ProviderQuotaExceeded,
    ProviderRateLimited,
    ProviderUnavailable,
)
from agent_dev_kit.providers.provider_anthropic import AnthropicProvider
from agent_dev_kit.providers.tool_loop import FunctionTool
from agent_dev_kit.runtime import DevAgentKit
from agent_dev_kit.tooling import ToolHandle


def text(value):
    return SimpleNamespace(type="text", text=value)


def tool_use(name, arguments=None, call_id="call_1"):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=arguments or {})


def message(*blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


def provider_with(responses, **kwargs):
    client = FakeClient(responses)
    provider = AnthropicProvider(
        default_model="claude-test",
        client=client,
        **kwargs,
    )
    return provider, client.messages


def definition(name, instructions="Instructions."):
    return AgentDefinition(name=name, instructions=instructions)


def test_text_answer_uses_agent_instructions_and_model():
    provider, messages = provider_with([message(text("Hola"))])
    agent = provider.create_agent(definition("Agent Backend", "Backend rules."))

    result = provider.run_sync(agent, "hola")

    assert result.output == "Hola"
    assert result.active_agent is agent
    call = messages.calls[0]
    assert call["model"] == "claude-test"
    assert call["system"] == "Backend rules."
    assert call["messages"] == [{"role": "user", "content": "hola"}]
    assert "tools" not in call


def test_handoff_switches_active_agent_and_keeps_history():
    provider, messages = provider_with(
        [
            message(tool_use("transfer_to_agent_backend"), stop_reason="tool_use"),
            message(text("Soy Backend")),
        ]
    )
    backend = provider.create_agent(definition("Agent Backend", "Backend rules."))
    triage = provider.create_agent(definition("Agent Triage", "Triage rules."))
    provider.set_handoffs(triage, (backend,))

    result = provider.run_sync(triage, "arreglá el endpoint")

    assert result.output == "Soy Backend"
    assert result.active_agent is backend
    first, second = messages.calls
    assert [tool["name"] for tool in first["tools"]] == ["transfer_to_agent_backend"]
    assert second["system"] == "Backend rules."
    assert second["messages"][1]["role"] == "assistant"
    assert second["messages"][2]["content"][0]["type"] == "tool_result"
    assert second["messages"][2]["content"][0]["tool_use_id"] == "call_1"


def test_structured_output_forces_tool_and_returns_mapping():
    payload = {"request": "x"}
    provider, messages = provider_with(
        [message(tool_use("submit_output", payload), stop_reason="tool_use")]
    )
    planner = provider.create_structured_agent(
        definition("Agent Triage Planner"),
        output_type=StructuredTaskPlan,
    )

    result = provider.run_sync(planner, "plan")

    assert result.output == payload
    call = messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "submit_output"}
    schema = call["tools"][0]["input_schema"]
    assert schema["type"] == "object"
    assert "nodes" in schema["required"]
    risk_items = schema["properties"]["profile"]["properties"]["risk_flags"]["items"]
    assert "backend_change" in risk_items["enum"]


def test_function_tool_runs_handler_and_returns_result_to_model():
    seen = []
    tool = FunctionTool(
        name="read_file",
        description="Read a file.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=lambda args: seen.append(args) or "contenido",
    )
    provider, messages = provider_with(
        [
            message(tool_use("read_file", {"path": "a.py"}), stop_reason="tool_use"),
            message(text("Listo")),
        ]
    )
    agent = provider.create_agent(
        definition("Agent Backend"),
        tools=(ToolHandle(provider="anthropic", key="read_file", native=tool),),
    )

    result = provider.run_sync(agent, "leé a.py")

    assert result.output == "Listo"
    assert seen == [{"path": "a.py"}]
    assert messages.calls[1]["messages"][2]["content"][0]["content"] == "contenido"


def test_missing_model_is_a_clear_error():
    provider = AnthropicProvider(client=FakeClient([]))

    with pytest.raises(ValueError, match="needs a model"):
        provider.create_agent(definition("Agent Backend"))


def _status_error(cls, status, body_message):
    response = httpx.Response(
        status,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        json={"type": "error", "error": {"message": body_message}},
    )
    return cls(body_message, response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            _status_error(
                anthropic.BadRequestError,
                400,
                "Your credit balance is too low to access the Anthropic API.",
            ),
            ProviderQuotaExceeded,
        ),
        (
            _status_error(anthropic.AuthenticationError, 401, "invalid x-api-key"),
            ProviderAuthenticationError,
        ),
        (
            _status_error(anthropic.RateLimitError, 429, "Rate limit exceeded"),
            ProviderRateLimited,
        ),
        (
            _status_error(anthropic.InternalServerError, 529, "Overloaded"),
            ProviderUnavailable,
        ),
    ],
)
def test_anthropic_errors_are_normalized(error, expected):
    provider, _ = provider_with([error])
    agent = provider.create_agent(definition("Agent Backend"))

    with pytest.raises(expected):
        provider.run_sync(agent, "hola")


def test_plan_and_execute_task_end_to_end_with_anthropic_provider():
    plan = {
        "request": "Fix backend behavior",
        "profile": {
            "summary": "Fix backend behavior.",
            "classification": "backend_bug",
            "risk_flags": ["backend_change"],
            "durable_artifacts": [],
        },
        "agent_decisions": [
            {
                "agent": "backend",
                "selected": True,
                "gate": "backend_change",
                "reason": "Backend behavior changes.",
            }
        ],
        "required_disabled_agents": [],
        "notes": None,
        "nodes": [
            {
                "id": "backend",
                "agent": "backend",
                "phase": "implementation",
                "objective": "Fix backend behavior",
                "depends_on": [],
            }
        ],
    }
    provider, messages = provider_with(
        [
            message(tool_use("submit_output", plan), stop_reason="tool_use"),
            message(text("Backend corregido.")),
        ]
    )
    config = ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="anthropic", default_model="claude-test"),
        enabled_agents=("triage", "backend"),
        agents={},
    )
    kit = DevAgentKit.build(config, provider)

    task = kit.plan_task_sync("Fix backend behavior")
    result = kit.execute_plan_sync(task)

    assert [node.status for node in result.nodes] == ["completed"]
    assert result.nodes[0].output == "Backend corregido."
    assert messages.calls[0]["tool_choice"]["name"] == "submit_output"
