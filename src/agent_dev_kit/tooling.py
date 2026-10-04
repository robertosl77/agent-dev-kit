from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(slots=True)
class ToolHandle:
    """Provider-specific native tool exposed through a neutral key."""

    provider: str
    key: str
    native: Any


class ToolRegistry:
    """Tools supplied by the consuming application at runtime."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolHandle] = {}

    def register(
        self,
        key: str,
        *,
        provider: str,
        native: Any,
    ) -> ToolHandle:
        normalized = self.normalize_key(key)
        if not normalized:
            raise ValueError("Tool key cannot be empty.")

        handle = ToolHandle(
            provider=provider.strip().lower(),
            key=normalized,
            native=native,
        )
        self._tools[normalized] = handle
        return handle

    def resolve(
        self,
        keys: Iterable[str],
        *,
        provider: str,
    ) -> tuple[ToolHandle, ...]:
        expected_provider = provider.strip().lower()
        resolved: list[ToolHandle] = []

        for raw_key in keys:
            key = self.normalize_key(raw_key)
            try:
                handle = self._tools[key]
            except KeyError as exc:
                raise ValueError(
                    f"Tool '{key}' is required but not registered."
                ) from exc

            if handle.provider != expected_provider:
                raise ValueError(
                    f"Tool '{key}' belongs to provider '{handle.provider}', "
                    f"not '{expected_provider}'."
                )

            resolved.append(handle)

        return tuple(resolved)

    @staticmethod
    def normalize_key(value: str) -> str:
        return value.strip().lower().replace("-", "_").replace(" ", "_")
