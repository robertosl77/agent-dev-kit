"""Build JSON Schemas from the dataclass contracts used for structured output.

Providers that enforce structured output through a forced tool call
(Anthropic, Gemini) need a plain JSON Schema. The contracts are small
dataclasses with enums, lists and optionals, so a focused converter is enough
and avoids adding a schema dependency to the core package.
"""

from __future__ import annotations

import dataclasses
import types
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints


_PRIMITIVES: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def json_schema_for(annotation: Any) -> dict[str, Any]:
    """Return a JSON Schema for a dataclass, enum, list, optional or primitive."""

    origin = get_origin(annotation)

    if origin in (Union, types.UnionType):
        arguments = [item for item in get_args(annotation) if item is not type(None)]
        nullable = len(arguments) != len(get_args(annotation))
        if len(arguments) != 1:
            raise TypeError(f"Unsupported union type: {annotation!r}")
        schema = json_schema_for(arguments[0])
        if nullable:
            schema = _make_nullable(schema)
        return schema

    if origin in (list, tuple):
        arguments = get_args(annotation)
        if not arguments:
            raise TypeError(f"List type needs an item type: {annotation!r}")
        return {"type": "array", "items": json_schema_for(arguments[0])}

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {
            "type": "string",
            "enum": [str(item.value) for item in annotation],
        }

    if isinstance(annotation, type) and annotation in _PRIMITIVES:
        return {"type": _PRIMITIVES[annotation]}

    if dataclasses.is_dataclass(annotation) and isinstance(annotation, type):
        hints = get_type_hints(annotation)
        properties = {
            field.name: json_schema_for(hints[field.name])
            for field in dataclasses.fields(annotation)
        }
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    raise TypeError(f"Unsupported type for JSON Schema: {annotation!r}")


def _make_nullable(schema: dict[str, Any]) -> dict[str, Any]:
    current = schema.get("type")
    if isinstance(current, str):
        return {**schema, "type": [current, "null"]}
    return {"anyOf": [schema, {"type": "null"}]}
