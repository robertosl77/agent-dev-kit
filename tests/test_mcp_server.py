import asyncio
from pathlib import Path

import pytest

from agent_dev_kit.gateway import AgentDevKitGateway
from agent_dev_kit.mcp_server import (
    _require_loopback_host,
    build_mcp_server,
)
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class SimpleProvider(AgentProvider):
    key = "fake"

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native=definition,
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        return ProviderRunResult(
            output=f"reply:{message}",
            active_agent=agent,
        )


def gateway(tmp_path):
    write(
        tmp_path / ".agent-dev-kit" / "project.yaml",
        """
project:
  name: MCPExample

provider:
  name: fake

agents:
  enabled:
    - triage
""",
    )
    registry = ProviderRegistry()
    registry.register("fake", lambda config: SimpleProvider())
    return AgentDevKitGateway(tmp_path, registry=registry)


def test_mcp_server_exposes_client_neutral_tools(tmp_path):
    from mcp import Client

    server = build_mcp_server(gateway(tmp_path))

    async def exercise():
        async with Client(server) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert names == {
                "agent_dev_kit_status",
                "agent_dev_kit_chat",
                "agent_dev_kit_chat_fallback",
                "agent_dev_kit_chat_reset",
                "agent_dev_kit_task",
                "agent_dev_kit_task_fallback",
                "agent_dev_kit_task_status",
                "agent_dev_kit_orchestration_proposals",
            }

            result = await client.call_tool(
                "agent_dev_kit_status",
                {},
            )
            assert result.structured_content["project"] == "MCPExample"
            assert result.is_error is False

            proposals = await client.call_tool(
                "agent_dev_kit_orchestration_proposals",
                {"min_occurrences": 3},
            )
            assert proposals.structured_content["status"] == "ok"
            assert proposals.structured_content["auto_modify"] is False
            assert proposals.structured_content["auto_create_issue"] is False

    asyncio.run(exercise())


def test_streamable_http_refuses_public_bind():
    with pytest.raises(ValueError, match="non-loopback"):
        _require_loopback_host("0.0.0.0")


def test_streamable_http_accepts_loopback():
    _require_loopback_host("127.0.0.1")
    _require_loopback_host("localhost")
    _require_loopback_host("::1")
