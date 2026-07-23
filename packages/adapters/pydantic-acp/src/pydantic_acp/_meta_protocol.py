from __future__ import annotations as _annotations

from typing import Any, Final, cast

from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.output import OutputSpec, StructuredDict
from pydantic_core import to_jsonable_python

from .session.state import JsonValue

__all__ = (
    "MISSING_STRUCTURED_OUTPUT",
    "build_structured_output_request_meta",
    "build_structured_output_response_meta",
    "build_structured_output_type",
    "extract_field_meta",
    "extract_structured_output",
    "has_structured_output_request",
)

_PYDANTIC_ACP_META_KEY: Final = "pydantic_acp"
_META_VERSION: Final = 1
_STRUCTURED_OUTPUT_KEY: Final = "structured_output"
_MISSING = object()
MISSING_STRUCTURED_OUTPUT: Final = _MISSING


def build_structured_output_request_meta(
    params: ModelRequestParameters,
) -> dict[str, JsonValue] | None:
    """Build the private ACP `_meta` extension for structured output requests."""
    if not params.output_tools:
        return None

    payload: dict[str, JsonValue] = {
        "version": _META_VERSION,
        _STRUCTURED_OUTPUT_KEY: {
            "output_mode": params.output_mode,
            "allow_text_output": params.allow_text_output,
            "output_tools": [_json_value(tool) for tool in params.output_tools],
        },
    }
    return {_PYDANTIC_ACP_META_KEY: payload}


def build_structured_output_response_meta(output: Any) -> dict[str, JsonValue]:
    """Build the private ACP `_meta` extension for an agent-produced output."""
    return {
        _PYDANTIC_ACP_META_KEY: {
            "version": _META_VERSION,
            _STRUCTURED_OUTPUT_KEY: {
                "output": _json_value(output),
            },
        },
    }


def build_structured_output_type(meta: Any) -> OutputSpec[Any] | None:
    """Build a Pydantic AI output spec from the schema carried in private `_meta`."""
    extension = _extension_payload(meta)
    if extension is None:
        return None
    structured = extension.get(_STRUCTURED_OUTPUT_KEY)
    if not isinstance(structured, dict):
        return None
    output_tools = structured.get("output_tools")
    if not isinstance(output_tools, list) or not output_tools:
        return None
    output_tool = output_tools[0]
    if not isinstance(output_tool, dict):
        return None
    json_schema = output_tool.get("parameters_json_schema")
    if not isinstance(json_schema, dict):
        return None
    name = output_tool.get("name")
    description = output_tool.get("description")
    return StructuredDict(
        cast(dict[str, Any], json_schema),
        name=name if isinstance(name, str) else None,
        description=description if isinstance(description, str) else None,
    )


def has_structured_output_request(meta: Any) -> bool:
    extension = _extension_payload(meta)
    if extension is None:
        return False
    return isinstance(extension.get(_STRUCTURED_OUTPUT_KEY), dict)


def extract_structured_output(meta: Any) -> JsonValue | object:
    extension = _extension_payload(meta)
    if extension is None:
        return MISSING_STRUCTURED_OUTPUT
    structured = extension.get(_STRUCTURED_OUTPUT_KEY)
    if not isinstance(structured, dict) or "output" not in structured:
        return MISSING_STRUCTURED_OUTPUT
    return structured["output"]


def extract_field_meta(value: Any) -> dict[str, Any] | None:
    """Read ACP `_meta` regardless of alias or generated field name."""
    if isinstance(value, dict):
        raw = value.get("_meta", value.get("field_meta"))
    else:
        raw = getattr(value, "field_meta", None)
        if raw is None:
            raw = getattr(value, "_meta", None)
    return raw if isinstance(raw, dict) else None


def _extension_payload(meta: Any) -> dict[str, Any] | None:
    if not isinstance(meta, dict):
        return None
    raw = meta.get(_PYDANTIC_ACP_META_KEY)
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != _META_VERSION:
        return None
    return raw


def _json_value(value: Any) -> JsonValue:
    return cast(
        JsonValue,
        to_jsonable_python(
            value,
            by_alias=True,
            exclude_none=True,
            fallback=repr,
        ),
    )
