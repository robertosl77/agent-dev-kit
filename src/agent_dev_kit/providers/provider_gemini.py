"""Google Gemini provider built on the official ``google-genai`` library."""

from __future__ import annotations

import os
from typing import Any, Mapping

from agent_dev_kit.providers.tool_loop import (
    LoopAgent,
    ModelTurn,
    ToolCall,
    ToolLoopProvider,
    ToolSpec,
)


GEMINI_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


class GeminiProvider(ToolLoopProvider):
    key = "gemini"
    env_var = "GEMINI_API_KEY"

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
        self._types = _genai_types()
        if self._client is None:
            self._client = build_gemini_client(
                api_key,
                base_url=self.options.get("base_url"),
            )

    def _new_transcript(self, message: str) -> list[Any]:
        types = self._types
        return [types.Content(role="user", parts=[types.Part(text=message)])]

    def _complete(
        self,
        spec: LoopAgent,
        transcript: list[Any],
        tools: list[ToolSpec],
        forced_tool: str | None,
    ) -> ModelTurn:
        types = self._types
        config_kwargs: dict[str, Any] = {
            "system_instruction": spec.definition.instructions,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        }
        if tools:
            config_kwargs["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=tool.name,
                            description=tool.description,
                            parameters_json_schema=dict(tool.parameters),
                        )
                        for tool in tools
                    ]
                )
            ]
        if forced_tool is not None:
            config_kwargs["tool_config"] = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[forced_tool],
                )
            )

        response = self._client.models.generate_content(
            model=spec.model,
            contents=transcript,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        candidates = getattr(response, "candidates", None) or []
        content = candidates[0].content if candidates else None
        texts: list[str] = []
        calls: list[ToolCall] = []
        for index, part in enumerate(getattr(content, "parts", None) or []):
            if getattr(part, "thought", False):
                continue
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                calls.append(
                    ToolCall(
                        id=function_call.id or f"call_{index}",
                        name=function_call.name,
                        arguments=dict(function_call.args or {}),
                    )
                )
            elif getattr(part, "text", None):
                texts.append(part.text)

        finish = getattr(candidates[0], "finish_reason", None) if candidates else None
        return ModelTurn(
            text="".join(texts),
            tool_calls=calls,
            raw=content,
            truncated=str(finish).upper().endswith("MAX_TOKENS"),
        )

    def _append_assistant(self, transcript: list[Any], turn: ModelTurn) -> None:
        # Keep the native content: Gemini needs its thought signatures back
        # when the conversation continues after a function call.
        if turn.raw is not None:
            transcript.append(turn.raw)

    def _append_tool_results(
        self,
        transcript: list[Any],
        results: list[tuple[ToolCall, str]],
    ) -> None:
        types = self._types
        transcript.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id,
                            name=call.name,
                            response={"result": output},
                        )
                    )
                    for call, output in results
                ],
            )
        )


def gemini_key_from_env() -> str | None:
    for name in GEMINI_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _genai_types():
    try:
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Gemini provider requires the optional dependency. "
            "Install with: pip install 'agent-dev-kit[gemini]'"
        ) from exc
    return types


def build_gemini_client(api_key: str | None, *, base_url: str | None = None):
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Gemini provider requires the optional dependency. "
            "Install with: pip install 'agent-dev-kit[gemini]'"
        ) from exc

    key = api_key or gemini_key_from_env()
    if not key:
        raise ValueError(
            "Gemini needs an API key: choose Gemini in the agent-dev-kit menu "
            "or set GEMINI_API_KEY."
        )
    kwargs: dict[str, Any] = {"api_key": key}
    if base_url:
        kwargs["http_options"] = types.HttpOptions(base_url=base_url)
    return genai.Client(**kwargs)
