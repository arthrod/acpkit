from __future__ import annotations as _annotations

from collections.abc import Iterable

__all__ = (
    "MCP_SERVERS_COMMAND_NAME",
    "MODEL_COMMAND_NAME",
    "RESERVED_SLASH_COMMAND_NAMES",
    "TOOLS_COMMAND_NAME",
    "validate_mode_command_ids",
)

MODEL_COMMAND_NAME = "model"
TOOLS_COMMAND_NAME = "tools"
MCP_SERVERS_COMMAND_NAME = "mcp-servers"
RESERVED_SLASH_COMMAND_NAMES = frozenset(
    {
        MODEL_COMMAND_NAME,
        TOOLS_COMMAND_NAME,
        MCP_SERVERS_COMMAND_NAME,
    },
)


def validate_mode_command_ids(mode_ids: Iterable[str]) -> None:
    normalized_ids: list[str] = []
    for mode_id in mode_ids:
        normalized_id = mode_id.strip().lower()
        if not normalized_id:
            raise ValueError("Mode slash command ids must be non-empty after normalization.")
        if any(character.isspace() for character in normalized_id):
            raise ValueError(
                f"Mode slash command id {mode_id!r} cannot contain whitespace after normalization.",
            )
        normalized_ids.append(normalized_id)
    duplicate_ids = sorted(
        mode_id for mode_id in set(normalized_ids) if normalized_ids.count(mode_id) > 1
    )
    if duplicate_ids:
        raise ValueError(f"Duplicate ids: {', '.join(duplicate_ids)}.")
    reserved_ids = sorted(set(normalized_ids) & RESERVED_SLASH_COMMAND_NAMES)
    if reserved_ids:
        raise ValueError(
            "Mode slash command ids cannot reuse reserved slash command names "
            f"({', '.join(reserved_ids)}).",
        )
