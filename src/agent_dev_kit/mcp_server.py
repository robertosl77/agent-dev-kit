from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_dev_kit.gateway import AgentDevKitGateway
from agent_dev_kit.preferences import PreferenceProfile
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.tooling import ToolRegistry


def build_mcp_server(
    gateway: AgentDevKitGateway,
):
    """Build an MCP server without coupling the gateway to MCP internals."""

    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is optional. Install Agent Dev Kit with "
            "pip install -e '.[mcp]'."
        ) from exc

    server = MCPServer(
        "Agent Dev Kit",
        instructions=(
            "Use these tools to work through the Agent Dev Kit bound to one "
            "software project. The server owns project selection, agent "
            "routing, multi-agent DAG execution, preferences and provider "
            "fallback state. Never invent disabled specialists."
        ),
    )

    @server.tool()
    def agent_dev_kit_status() -> dict[str, Any]:
        """Inspect the bound project, enabled agents and provider policy."""

        return gateway.status()

    @server.tool()
    def agent_dev_kit_chat(
        message: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to a persistent Agent Dev Kit conversation.

        Reuse the returned session_id for follow-up messages. If the response
        is fallback_required, ask the user before calling
        agent_dev_kit_chat_fallback.
        """

        return gateway.chat(
            message,
            session_id=session_id,
        )

    @server.tool()
    def agent_dev_kit_chat_fallback(
        session_id: str,
        approve: bool,
    ) -> dict[str, Any]:
        """Approve or reject a provider fallback for one chat session."""

        return gateway.chat_fallback(
            session_id,
            approve=approve,
        )

    @server.tool()
    def agent_dev_kit_chat_reset(
        session_id: str,
    ) -> dict[str, Any]:
        """Discard one Agent Dev Kit conversation and its neutral transcript."""

        return gateway.reset_chat(session_id)

    @server.tool()
    def agent_dev_kit_task(
        request: str,
    ) -> dict[str, Any]:
        """Plan and execute a multi-specialist task through the task DAG.

        If a required specialist is disabled, returns status=blocked.
        If provider fallback needs approval, returns status=fallback_required
        with a task_id that must be reused in agent_dev_kit_task_fallback.
        """

        return gateway.start_task(request)

    @server.tool()
    def agent_dev_kit_task_fallback(
        task_id: str,
        approve: bool,
    ) -> dict[str, Any]:
        """Approve or reject provider fallback and resume the same task DAG."""

        return gateway.task_fallback(
            task_id,
            approve=approve,
        )

    @server.tool()
    def agent_dev_kit_task_status(
        task_id: str,
    ) -> dict[str, Any]:
        """Inspect a task DAG and its completed/pending nodes."""

        return gateway.task_status(task_id)

    return server


def run_mcp_server(
    project_root: str | Path = ".",
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    registry: ProviderRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
    preference_profile: PreferenceProfile | None = None,
) -> None:
    """Run Agent Dev Kit as a standard MCP server.

    v0.1.0 deliberately binds Streamable HTTP to loopback only. Remote access
    should be supplied by a trusted MCP tunnel or authenticated reverse proxy,
    rather than exposing an unauthenticated development server.
    """

    normalized_transport = transport.strip().lower()
    if normalized_transport not in {"stdio", "streamable-http"}:
        raise ValueError(
            "transport must be 'stdio' or 'streamable-http'."
        )

    if normalized_transport == "streamable-http":
        _require_loopback_host(host)

    gateway = AgentDevKitGateway(
        project_root,
        registry=registry,
        tool_registry=tool_registry,
        preference_profile=preference_profile,
    )
    server = build_mcp_server(gateway)

    if normalized_transport == "stdio":
        server.run(transport="stdio")
        return

    server.run(
        transport="streamable-http",
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
    )


def _require_loopback_host(host: str) -> None:
    normalized = host.strip().lower()
    if normalized not in {
        "127.0.0.1",
        "localhost",
        "::1",
        "[::1]",
    }:
        raise ValueError(
            "Agent Dev Kit refuses to expose the MCP server directly on a "
            "non-loopback interface in this release. Bind to localhost and "
            "use a trusted MCP tunnel or authenticated reverse proxy for "
            "remote clients."
        )
