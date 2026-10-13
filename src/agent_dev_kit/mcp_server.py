from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_dev_kit.gateway import AgentDevKitGateway
from agent_dev_kit.preferences import PreferenceProfile
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.tooling import ToolRegistry


def build_mcp_server(
    gateway: AgentDevKitGateway,
    *,
    allow_actions: bool = False,
):
    """Build an MCP server without coupling the gateway to MCP internals."""

    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is optional. Install Agent Dev Kit with "
            "pip install -e '.[mcp]'."
        ) from exc

    gateway.workflow.allow_actions = bool(allow_actions)

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


    # Resumable CLI-parity workflows. Legacy task/chat names stay supported.
    @server.tool()
    def agent_dev_kit_workflow_start(
        request: str, mode: str = "propose", issue: str | None = None,
    ) -> dict[str, Any]:
        """Start /plan, /task or /do through the shared engine.

        mode=plan: Triage only. mode=propose: read-only inspection and
        specialist proposals. mode=act: gated Git mutations, only if the
        server owner explicitly enabled MCP action mode. Inspect every
        approval_required response and ask the human before deciding.
        """
        return gateway.workflow.start(request, mode=mode, issue=issue)

    @server.tool()
    def agent_dev_kit_workflow_status(workflow_id: str) -> dict[str, Any]:
        """Read workflow state, pending user decision, evidence and diff."""
        return gateway.workflow.status(workflow_id)

    @server.tool()
    def agent_dev_kit_workflow_decide(
        workflow_id: str, decision_id: str, approve: bool,
    ) -> dict[str, Any]:
        """Submit one explicit human decision for this pending stage.

        Requires a matching one-time decision_id from workflow_status.
        The MCP client MUST get fresh consent from the person; prior
        approval or generic repository permission is not enough.
        """
        return gateway.workflow.decide(workflow_id, decision_id, approve)

    @server.tool()
    def agent_dev_kit_workflow_issue(
        workflow_id: str, issue: str,
    ) -> dict[str, Any]:
        """Supply a user-approved issue reference for a gated action task."""
        return gateway.workflow.provide_issue(workflow_id, issue)

    @server.tool()
    def agent_dev_kit_workflow_fallback(
        workflow_id: str, approve: bool,
    ) -> dict[str, Any]:
        """Approve or reject one provider fallback without losing the workflow."""
        return gateway.workflow.fallback(workflow_id, approve)

    @server.tool()
    def agent_dev_kit_workflow_resume(
        workflow_id: str, approve: bool,
    ) -> dict[str, Any]:
        """Explicitly retry a safe interrupted phase after a process restart.

        No write-capable agent is ever replayed if action execution was
        interrupted; such a workflow requires manual worktree review.
        """
        return gateway.workflow.resume(workflow_id, approve)

    @server.tool()
    def agent_dev_kit_workflow_cancel(workflow_id: str) -> dict[str, Any]:
        """Cancel a workflow; never silently discard local code changes."""
        return gateway.workflow.cancel(workflow_id)

    @server.tool()
    def agent_dev_kit_repo_status() -> dict[str, Any]:
        """Inspect current branch, uncommitted changes and diff summary."""
        return gateway.workflow.repository_status()

    @server.tool()
    def agent_dev_kit_workflow_usage(workflow_id: str) -> dict[str, Any]:
        """Read token usage by agent and cost estimate when prices are configured."""
        return gateway.workflow.usage(workflow_id)

    @server.tool()
    def agent_dev_kit_graphs(limit: int = 20) -> dict[str, Any]:
        """Read persisted orchestration graph summaries (no mutation)."""
        return gateway.workflow.graphs(limit)

    @server.tool()
    def agent_dev_kit_candidates() -> dict[str, Any]:
        """Read deterministic routing improvement analysis (no mutation)."""
        return gateway.workflow.candidates()

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
    allow_actions: bool = False,
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
    server = build_mcp_server(gateway, allow_actions=allow_actions)

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
