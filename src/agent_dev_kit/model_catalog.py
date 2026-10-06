"""Live model listing per provider.

The list always comes from the provider's own API with the person's key:
there is no hard-coded model list to maintain (M-073, decision 3). Tags only
show what the provider itself reports (decision 3b): nothing is guessed from
model names. The "thinking" capability is not shown because every current chat
model reports it, so it does not distinguish models (M-075).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class ModelOption:
    id: str
    label: str
    tags: tuple[str, ...] = ()


# OpenAI lists every model it serves (embeddings, audio, images...). Only chat
# models are useful here. Same filter Librería Inglés uses for its own menu.
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "o5", "chatgpt-")
_OPENAI_EXCLUDE = (
    "embedding", "tts", "whisper", "audio", "realtime", "transcribe", "image",
    "dall-e", "search", "moderation", "instruct", "codex", "computer-use",
)
_GEMINI_EXCLUDE = ("embedding", "aqa", "imagen", "tts", "image", "veo", "live")


def list_models(
    provider: str,
    api_key: str | None,
    *,
    client: Any | None = None,
    base_url: str | None = None,
) -> list[ModelOption]:
    """Return the provider's chat models, newest first when it reports dates."""

    key = provider.strip().lower()
    try:
        lister = _LISTERS[key]
    except KeyError as exc:
        raise ValueError(f"Model listing is not available for '{provider}'.") from exc
    return lister(api_key, client, base_url)


def _list_anthropic(api_key, client, base_url) -> list[ModelOption]:
    if client is None:
        from agent_dev_kit.providers.provider_anthropic import build_anthropic_client

        client = build_anthropic_client(api_key, base_url=base_url)

    rows = list(client.models.list(limit=100))
    rows.sort(key=lambda item: str(getattr(item, "created_at", "") or ""), reverse=True)

    options = []
    for item in rows:
        tags: list[str] = []
        line = getattr(item, "line", None)
        if line is None:
            line = (getattr(item, "model_extra", None) or {}).get("line")
        if line:
            tags.append(f"línea {line}")
        options.append(
            ModelOption(
                id=item.id,
                label=getattr(item, "display_name", None) or item.id,
                tags=tuple(tags),
            )
        )
    return options


def _list_gemini(api_key, client, base_url) -> list[ModelOption]:
    if client is None:
        from agent_dev_kit.providers.provider_gemini import build_gemini_client

        client = build_gemini_client(api_key, base_url=base_url)

    options = []
    for item in client.models.list():
        name = str(getattr(item, "name", "") or "")
        model_id = name.removeprefix("models/")
        actions = getattr(item, "supported_actions", None) or []
        if "generateContent" not in actions:
            continue
        if not model_id.startswith("gemini") or any(
            word in model_id for word in _GEMINI_EXCLUDE
        ):
            continue
        options.append(
            ModelOption(
                id=model_id,
                label=getattr(item, "display_name", None) or model_id,
            )
        )
    return options


def _list_openai(api_key, client, base_url) -> list[ModelOption]:
    if client is None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI provider requires the optional dependency. "
                "Install with: pip install 'agent-dev-kit[openai]'"
            ) from exc
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)

    rows = [
        item
        for item in client.models.list()
        if str(item.id).startswith(_OPENAI_CHAT_PREFIXES)
        and not any(word in item.id for word in _OPENAI_EXCLUDE)
    ]
    rows.sort(key=lambda item: int(getattr(item, "created", 0) or 0), reverse=True)
    # OpenAI does not report reasoning or speed in this list, so no tags.
    return [ModelOption(id=item.id, label=item.id) for item in rows]


_LISTERS: dict[str, Callable[[str | None, Any, str | None], list[ModelOption]]] = {
    "anthropic": _list_anthropic,
    "gemini": _list_gemini,
    "openai": _list_openai,
}
