"""Shared agent loop for providers integrated through their official SDKs.

OpenAI is integrated through the OpenAI Agents SDK, which already implements
the agent loop. Anthropic and Gemini are integrated directly with their
official client libraries (decision 4 of M-073), so Agent Dev Kit owns the
small loop those SDKs do not provide:

    user message
      └─► model turn ──► text only ───────────────► final result
                    ├─► transfer_to_<agent> tool ─► continue with that agent
                    ├─► consumer tool ────────────► run handler, continue
                    └─► submit_output tool ───────► structured final result

Concrete providers implement only the SDK-specific pieces: one model call
and how messages are appended to the native transcript.
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.provider_errors import (
    ProviderError,
    ProviderExecutionError,
    normalize_provider_exception,
)
from agent_dev_kit.providers.json_schema import json_schema_for
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)
from agent_dev_kit.tooling import ToolHandle
from agent_dev_kit.usage import UsageRecord


STRUCTURED_OUTPUT_TOOL = "submit_output"
DEFAULT_MAX_TURNS = 25


@dataclass(frozen=True, slots=True)
class FunctionTool:
    """Native tool format for loop-based providers (Anthropic, Gemini).

    Register it in a ToolRegistry with ``provider="anthropic"`` or
    ``provider="gemini"``. ``handler`` receives the parsed arguments and its
    return value is sent back to the model as text.
    """

    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Provider-neutral tool description handed to the concrete provider."""

    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ModelTurn:
    """Normalized result of one model call."""

    text: str
    tool_calls: list[ToolCall]
    raw: Any = None
    truncated: bool = False
    usage: UsageRecord | None = None


@dataclass(slots=True)
class LoopAgent:
    """Native agent object for loop-based providers."""

    definition: AgentDefinition
    model: str
    handoffs: list[AgentHandle] = field(default_factory=list)
    tools: list[FunctionTool] = field(default_factory=list)
    output_schema: dict[str, Any] | None = None


class ToolLoopProvider(AgentProvider):
    """Base class for providers that run the agent loop inside Agent Dev Kit."""

    key: str
    env_var: str

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        options: Mapping[str, Any] | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.options = dict(options or {})
        self.max_turns = int(self.options.get("max_turns", DEFAULT_MAX_TURNS))
        self._client = client

    # ------------------------------------------------------------------ agents

    def create_agent(
        self,
        definition: AgentDefinition,
        *,
        handoffs: Sequence[AgentHandle] = (),
        tools: Sequence[ToolHandle] = (),
    ) -> AgentHandle:
        self._validate_handoffs(handoffs)
        self._validate_tools(tools)
        native_tools = []
        for tool in tools:
            if not isinstance(tool.native, FunctionTool):
                raise ValueError(
                    f"Tool '{tool.key}' for provider '{self.key}' must be a "
                    "FunctionTool."
                )
            native_tools.append(tool.native)

        native = LoopAgent(
            definition=definition,
            model=self._resolve_model(definition),
            handoffs=list(handoffs),
            tools=native_tools,
        )
        return AgentHandle(provider=self.key, name=definition.name, native=native)

    def supports_structured_output(self) -> bool:
        return True

    def native_tool(self, tool: Any) -> FunctionTool:
        from agent_dev_kit.workspace_tools import safe_handler

        return FunctionTool(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            handler=safe_handler(tool),
        )

    def create_structured_agent(
        self,
        definition: AgentDefinition,
        *,
        output_type: type[Any],
    ) -> AgentHandle:
        native = LoopAgent(
            definition=definition,
            model=self._resolve_model(definition),
            output_schema=json_schema_for(output_type),
        )
        return AgentHandle(provider=self.key, name=definition.name, native=native)

    def set_handoffs(
        self,
        agent: AgentHandle,
        handoffs: Sequence[AgentHandle],
    ) -> None:
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)
        agent.native.handoffs = list(handoffs)

    def _resolve_model(self, definition: AgentDefinition) -> str:
        model = (definition.model or self.default_model or "").strip()
        if not model:
            raise ValueError(
                f"Provider '{self.key}' needs a model. Choose one in the "
                "agent-dev-kit menu or set provider.default_model in "
                ".agent-dev-kit/project.yaml."
            )
        return model

    # --------------------------------------------------------------------- run

    async def run(
        self,
        agent: AgentHandle,
        message: str,
        *,
        session: Any | None = None,
    ) -> ProviderRunResult:
        return await asyncio.to_thread(
            self.run_sync,
            agent,
            message,
            session=session,
        )

    def run_sync(
        self,
        agent: AgentHandle,
        message: str,
        *,
        session: Any | None = None,
    ) -> ProviderRunResult:
        # Conversation history is rebuilt by the CLI and the gateway as a
        # provider-neutral transcript, so a native session is not needed.
        self._validate_handle(agent)
        try:
            return self._run_loop(agent, message)
        except ProviderError:
            raise
        except Exception as exc:
            raise normalize_provider_exception(exc, provider=self.key) from exc

    def _run_loop(self, agent: AgentHandle, message: str) -> ProviderRunResult:
        current = agent
        transcript = self._new_transcript(message)
        usage: list[UsageRecord] = []

        def result(output: Any, active: AgentHandle, raw: Any) -> ProviderRunResult:
            return ProviderRunResult(
                output=output,
                active_agent=active,
                native_result=raw,
                usage=_merge(usage),
            )

        for _ in range(self.max_turns):
            spec: LoopAgent = current.native
            handoff_tools = {
                handoff_tool_name(item.name): item for item in spec.handoffs
            }
            function_tools = {tool.name: tool for tool in spec.tools}
            tool_specs = self._tool_specs(spec, handoff_tools)
            forced = (
                STRUCTURED_OUTPUT_TOOL if spec.output_schema is not None else None
            )

            turn = self._complete(spec, transcript, tool_specs, forced)
            if turn.usage is not None:
                usage.append(turn.usage)

            if forced is not None:
                for call in turn.tool_calls:
                    if call.name == STRUCTURED_OUTPUT_TOOL:
                        return result(call.arguments, current, turn.raw)
                raise ProviderExecutionError(
                    f"Provider '{self.key}' did not return the structured "
                    "output"
                    + (" (response truncated by max_tokens)." if turn.truncated else "."),
                    provider=self.key,
                )

            if not turn.tool_calls:
                return result(turn.text, current, turn.raw)

            self._append_assistant(transcript, turn)
            results: list[tuple[ToolCall, str]] = []
            next_agent: AgentHandle | None = None
            for call in turn.tool_calls:
                if call.name in handoff_tools:
                    target = handoff_tools[call.name]
                    next_agent = next_agent or target
                    results.append(
                        (call, json.dumps({"assistant": target.name}))
                    )
                elif call.name in function_tools:
                    results.append(
                        (call, _run_function_tool(function_tools[call.name], call))
                    )
                else:
                    results.append(
                        (call, f"Error: unknown tool '{call.name}'.")
                    )
            self._append_tool_results(transcript, results)
            if next_agent is not None:
                current = next_agent

        raise ProviderExecutionError(
            f"Provider '{self.key}' exceeded {self.max_turns} turns without a "
            "final answer.",
            provider=self.key,
        )

    def _tool_specs(
        self,
        spec: LoopAgent,
        handoff_tools: Mapping[str, AgentHandle],
    ) -> list[ToolSpec]:
        if spec.output_schema is not None:
            return [
                ToolSpec(
                    name=STRUCTURED_OUTPUT_TOOL,
                    description="Return the final structured result.",
                    parameters=spec.output_schema,
                )
            ]

        tools = [
            ToolSpec(
                name=name,
                description=(
                    f"Transfer the conversation to {target.name}. "
                    + (target.native.definition.handoff_description or "")
                ).strip(),
                parameters={"type": "object", "properties": {}},
            )
            for name, target in handoff_tools.items()
        ]
        tools.extend(
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
            )
            for tool in spec.tools
        )
        return tools

    # ------------------------------------------------------- SDK-specific API

    @abstractmethod
    def _new_transcript(self, message: str) -> list[Any]:
        """Return the native transcript holding the first user message."""

    @abstractmethod
    def _complete(
        self,
        spec: LoopAgent,
        transcript: list[Any],
        tools: list[ToolSpec],
        forced_tool: str | None,
    ) -> ModelTurn:
        """Make one model call and normalize its result."""

    @abstractmethod
    def _append_assistant(self, transcript: list[Any], turn: ModelTurn) -> None:
        """Append the assistant turn (with its tool calls) to the transcript."""

    @abstractmethod
    def _append_tool_results(
        self,
        transcript: list[Any],
        results: list[tuple[ToolCall, str]],
    ) -> None:
        """Append tool results so the model can continue."""


def _merge(records: list[UsageRecord]) -> list[UsageRecord]:
    from agent_dev_kit.usage import merge_usage

    return merge_usage(records)


def handoff_tool_name(agent_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", agent_name.lower()).strip("_")
    return f"transfer_to_{slug}"[:64]


def _run_function_tool(tool: FunctionTool, call: ToolCall) -> str:
    try:
        result = tool.handler(dict(call.arguments))
    except Exception as exc:  # the model receives the failure and can recover
        return f"Error running tool '{tool.name}': {exc}"
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)
