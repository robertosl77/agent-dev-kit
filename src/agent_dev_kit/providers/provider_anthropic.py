"""Anthropic (Claude) provider built on the official ``anthropic`` library."""

from __future__ import annotations

from typing import Any, Mapping

from agent_dev_kit.usage import UsageRecord
from agent_dev_kit.providers.tool_loop import (
    LoopAgent,
    ModelTurn,
    ToolCall,
    ToolLoopProvider,
    ToolSpec,
)


DEFAULT_MAX_TOKENS = 8192


class AnthropicProvider(ToolLoopProvider):
    key = "anthropic"
    env_var = "ANTHROPIC_API_KEY"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        options: Mapping[str, Any] | None = None,
        client: Any | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            default_model=default_model,
            options=options,
            client=client,
        )
        self.max_tokens = int(self.options.get("max_tokens", DEFAULT_MAX_TOKENS))
        if self._client is None:
            self._client = build_anthropic_client(
                api_key,
                base_url=self.options.get("base_url"),
            )

    def _new_transcript(self, message: str) -> list[Any]:
        return [{"role": "user", "content": message}]

    def _complete(
        self,
        spec: LoopAgent,
        transcript: list[Any],
        tools: list[ToolSpec],
        forced_tool: str | None,
    ) -> ModelTurn:
        kwargs: dict[str, Any] = {
            "model": spec.model,
            "max_tokens": self.max_tokens,
            "system": spec.definition.instructions,
            "messages": transcript,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": dict(tool.parameters),
                }
                for tool in tools
            ]
        if forced_tool is not None:
            kwargs["tool_choice"] = {"type": "tool", "name": forced_tool}

        response = self._client.messages.create(**kwargs)

        texts: list[str] = []
        calls: list[ToolCall] = []
        for block in response.content or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                texts.append(block.text)
            elif block_type == "tool_use":
                calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input or {}),
                    )
                )

        return ModelTurn(
            text="".join(texts),
            tool_calls=calls,
            raw=response,
            truncated=getattr(response, "stop_reason", None) == "max_tokens",
            usage=_anthropic_usage(response, spec.model),
        )

    def _append_assistant(self, transcript: list[Any], turn: ModelTurn) -> None:
        content: list[dict[str, Any]] = []
        if turn.text:
            content.append({"type": "text", "text": turn.text})
        content.extend(
            {
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": call.arguments,
            }
            for call in turn.tool_calls
        )
        transcript.append({"role": "assistant", "content": content})

    def _append_tool_results(
        self,
        transcript: list[Any],
        results: list[tuple[ToolCall, str]],
    ) -> None:
        transcript.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": output,
                    }
                    for call, output in results
                ],
            }
        )


def _anthropic_usage(response: Any, model: str) -> UsageRecord | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    cached = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    created = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return UsageRecord(
        provider="anthropic",
        model=str(getattr(response, "model", None) or model),
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0) + cached + created,
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cached_input_tokens=cached,
    )


def build_anthropic_client(api_key: str | None, *, base_url: str | None = None):
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "Anthropic provider requires the optional dependency. "
            "Install with: pip install 'agent-dev-kit[anthropic]'"
        ) from exc

    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.Anthropic(**kwargs)
