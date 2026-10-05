import asyncio

import pytest

pytest.importorskip("agents")

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.planner_contract import StructuredTaskPlan
from agent_dev_kit.providers.provider_openai import OpenAIProvider


class _FakeRunResult:
    def __init__(self, agent, output):
        self.last_agent = agent
        self.final_output = output


class _FakeRunner:
    @staticmethod
    def run_sync(agent, message, **kwargs):
        return _FakeRunResult(agent, f"echo:{message}")

    @staticmethod
    async def run(agent, message, **kwargs):
        return _FakeRunResult(agent, f"echo:{message}")


def test_openai_provider_creates_native_agents_and_handoffs_without_api_call():
    provider = OpenAIProvider()

    backend = provider.create_agent(
        AgentDefinition(
            name="Agent Backend",
            instructions="Backend instructions.",
        )
    )
    triage = provider.create_agent(
        AgentDefinition(
            name="Agent Triage",
            instructions="Triage instructions.",
        ),
        handoffs=(backend,),
    )

    assert backend.provider == "openai"
    assert triage.provider == "openai"
    assert triage.native.handoffs == [backend.native]


def test_openai_provider_accepts_structured_task_plan_output_type():
    provider = OpenAIProvider()

    planner = provider.create_structured_agent(
        AgentDefinition(
            name="Agent Triage Planner",
            instructions="Return a structured task plan.",
        ),
        output_type=StructuredTaskPlan,
    )

    assert planner.provider == "openai"
    assert planner.native.output_type is StructuredTaskPlan


def test_openai_provider_normalizes_sync_result_without_network():
    provider = OpenAIProvider()
    provider._runner = _FakeRunner

    backend = provider.create_agent(
        AgentDefinition(
            name="Agent Backend",
            instructions="Backend instructions.",
        )
    )

    result = provider.run_sync(backend, "hello")

    assert result.output == "echo:hello"
    assert result.active_agent.name == "Agent Backend"
    assert result.active_agent.native is backend.native


def test_openai_provider_normalizes_async_result_without_network():
    provider = OpenAIProvider()
    provider._runner = _FakeRunner

    backend = provider.create_agent(
        AgentDefinition(
            name="Agent Backend",
            instructions="Backend instructions.",
        )
    )

    result = asyncio.run(provider.run(backend, "hello"))

    assert result.output == "echo:hello"
    assert result.active_agent.name == "Agent Backend"
    assert result.active_agent.native is backend.native
