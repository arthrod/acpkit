from __future__ import annotations as _annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from acp.schema import (
    AvailableCommand,
    AvailableCommandInput,
    SessionMode,
    SessionModelState,
    SessionModeState,
    UnstructuredCommandInput,
)

from .._slash_commands import (
    MCP_SERVERS_COMMAND_NAME,
    MODEL_COMMAND_NAME,
    RESERVED_SLASH_COMMAND_NAMES,
    TOOLS_COMMAND_NAME,
    validate_mode_command_ids,
)
from ..session.state import AcpSessionContext, JsonValue

__all__ = (
    "McpServerInfo",
    "SlashCommand",
    "ToolInfo",
    "build_available_commands",
    "extract_session_mcp_servers",
    "list_graph_tools",
    "parse_slash_command",
    "render_mcp_server_listing",
    "render_mode_message",
    "render_model_message",
    "render_tool_listing",
    "validate_custom_commands",
)

_COMMAND_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(slots=True, frozen=True, kw_only=True)
class SlashCommand:
    name: str
    argument: str | None = None


@dataclass(slots=True, frozen=True, kw_only=True)
class ToolInfo:
    name: str
    description: str | None


@dataclass(slots=True, frozen=True, kw_only=True)
class McpServerInfo:
    name: str
    transport: str
    target: str
    source: str


def build_available_commands(
    *,
    mode_state: SessionModeState | None,
    model_state: SessionModelState | None,
    custom_commands: Sequence[AvailableCommand] | None = None,
) -> list[AvailableCommand]:
    commands: list[AvailableCommand] = []
    if mode_state is not None:
        validate_mode_command_ids(mode.id for mode in mode_state.available_modes)
        commands.extend(_mode_commands(mode_state.available_modes))
    if model_state is not None:
        commands.append(
            AvailableCommand(
                name=MODEL_COMMAND_NAME,
                description="Show the current session model, or set it with a provider:model value.",
                input=AvailableCommandInput(root=UnstructuredCommandInput(hint="provider:model")),
            ),
        )
    commands.extend(
        [
            AvailableCommand(
                name=TOOLS_COMMAND_NAME,
                description="List the tools currently registered on the active graph.",
            ),
            AvailableCommand(
                name=MCP_SERVERS_COMMAND_NAME,
                description="List MCP servers attached to the current session.",
            ),
        ],
    )
    if custom_commands:
        validate_custom_commands(custom_commands, mode_state=mode_state)
        commands.extend(custom_commands)
    return commands


def validate_custom_commands(
    commands: Sequence[AvailableCommand],
    *,
    mode_state: SessionModeState | None,
) -> None:
    normalized_names: list[str] = []
    for command in commands:
        normalized_name = command.name.strip().lower()
        if command.name != normalized_name:
            raise ValueError(
                f"Slash command name {command.name!r} must already be normalized as "
                "a lowercase slash command id.",
            )
        if not _COMMAND_NAME_PATTERN.fullmatch(normalized_name):
            raise ValueError(f"Slash command name {command.name!r} must match ^[a-z][a-z0-9-]*$.")
        normalized_names.append(normalized_name)
    duplicate_names = sorted(
        name for name in set(normalized_names) if normalized_names.count(name) > 1
    )
    if duplicate_names:
        raise ValueError(
            "Custom slash command names must be unique after normalization. "
            f"Duplicate ids: {', '.join(duplicate_names)}.",
        )
    reserved_names = sorted(set(normalized_names) & RESERVED_SLASH_COMMAND_NAMES)
    if reserved_names:
        raise ValueError(
            "Custom slash command names cannot reuse reserved slash command names "
            f"({', '.join(reserved_names)}).",
        )
    if mode_state is None:
        return
    mode_ids = {mode.id.strip().lower() for mode in mode_state.available_modes}
    conflicting_mode_ids = sorted(set(normalized_names) & mode_ids)
    if conflicting_mode_ids:
        raise ValueError(
            "Custom slash command names cannot reuse active mode ids "
            f"({', '.join(conflicting_mode_ids)}).",
        )


def parse_slash_command(prompt_text: str) -> SlashCommand | None:
    stripped = prompt_text.strip()
    if not stripped.startswith("/"):
        return None
    command_text = stripped[1:]
    if not command_text.strip():
        return None
    name, _, remainder = command_text.partition(" ")
    normalized_name = name.strip().lower()
    if not normalized_name:
        return None
    argument = remainder.strip() or None
    return SlashCommand(name=normalized_name, argument=argument)


def render_mode_message(current_mode_id: str | None) -> str:
    if current_mode_id is None:
        return "Current mode: unavailable"
    return f"Current mode: {current_mode_id}"


def render_model_message(current_model_id: str | None) -> str:
    if current_model_id is None:
        return "Current model: unavailable"
    return f"Current model: {current_model_id}"


def render_tool_listing(tool_infos: list[ToolInfo]) -> str:
    if not tool_infos:
        return "No tools are currently registered."
    lines = ["Available tools:"]
    for tool_info in tool_infos:
        if tool_info.description is not None:
            lines.append(f"- {tool_info.name}: {tool_info.description}")
        else:
            lines.append(f"- {tool_info.name}")
    return "\n".join(lines)


def render_mcp_server_listing(server_infos: list[McpServerInfo]) -> str:
    if not server_infos:
        return "No MCP servers are currently attached."
    lines = ["MCP servers:"]
    for server_info in server_infos:
        lines.append(
            f"- {server_info.name} ({server_info.transport}, {server_info.source}): "
            f"{server_info.target}",
        )
    return "\n".join(lines)


def list_graph_tools(graph: Any) -> list[ToolInfo]:
    graph_view_factory = getattr(graph, "get_graph", None)
    if not callable(graph_view_factory):
        return []
    graph_view = graph_view_factory()
    nodes = getattr(graph_view, "nodes", None)
    if not isinstance(nodes, dict):
        return []
    tool_infos: list[ToolInfo] = []
    for node in nodes.values():
        tool_node = getattr(node, "data", None)
        tools_by_name = getattr(tool_node, "_tools_by_name", None)
        if not isinstance(tools_by_name, dict):
            continue
        string_items = [
            (name, tool) for name, tool in tools_by_name.items() if isinstance(name, str)
        ]
        for name, tool in sorted(string_items, key=lambda item: item[0]):
            description = getattr(tool, "description", None)
            tool_infos.append(
                ToolInfo(
                    name=name,
                    description=description if isinstance(description, str) else None,
                ),
            )
    return tool_infos


def extract_session_mcp_servers(session: AcpSessionContext) -> list[McpServerInfo]:
    server_infos: list[McpServerInfo] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_server in session.mcp_servers:
        server_info = _mcp_server_info_from_session_payload(raw_server)
        if server_info is None:
            continue
        dedupe_key = (
            server_info.name,
            server_info.transport,
            server_info.target,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        server_infos.append(server_info)
    metadata_servers = session.metadata.get("mcp")
    if not isinstance(metadata_servers, dict):
        return server_infos
    raw_servers = metadata_servers.get("servers")
    if not isinstance(raw_servers, list):
        return server_infos
    for raw_server in raw_servers:
        server_info = _mcp_server_info_from_bridge_metadata(raw_server)
        if server_info is None:
            continue
        dedupe_key = (
            server_info.name,
            server_info.transport,
            server_info.target,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        server_infos.append(server_info)
    return server_infos


def _mode_commands(modes: Sequence[SessionMode]) -> list[AvailableCommand]:
    return [
        AvailableCommand(
            name=mode.id,
            description=mode.description or f"Switch the active session into {mode.name} mode.",
        )
        for mode in modes
    ]


def _mcp_server_info_from_session_payload(
    raw_server: dict[str, JsonValue],
) -> McpServerInfo | None:
    name = raw_server.get("name")
    if not isinstance(name, str) or not name:
        return None
    transport = raw_server.get("type")
    if not isinstance(transport, str) or not transport:
        transport = raw_server.get("transport")
    if not isinstance(transport, str) or not transport:
        return None
    if transport == "stdio":
        command = raw_server.get("command")
        args = raw_server.get("args")
        rendered_args = (
            " ".join(item for item in args if isinstance(item, str))
            if isinstance(args, list)
            else ""
        )
        target = command if isinstance(command, str) else "<stdio>"
        if rendered_args:
            target = f"{target} {rendered_args}"
    else:
        url = raw_server.get("url")
        target = url if isinstance(url, str) and url else f"<{transport}>"
    return McpServerInfo(
        name=name,
        transport=transport,
        target=target,
        source="session",
    )


def _mcp_server_info_from_bridge_metadata(raw_server: JsonValue) -> McpServerInfo | None:
    raw_server_dict = _string_key_dict(raw_server)
    if raw_server_dict is None:
        return None
    name = raw_server_dict.get("name")
    transport = raw_server_dict.get("transport")
    if not isinstance(name, str) or not isinstance(transport, str):
        return None
    url = raw_server_dict.get("url")
    description = raw_server_dict.get("description")
    target_parts = [value for value in (url, description) if isinstance(value, str) and value]
    target = " | ".join(target_parts) if target_parts else f"<{transport}>"
    return McpServerInfo(
        name=name,
        transport=transport,
        target=target,
        source="bridge",
    )


def _string_key_dict(value: JsonValue) -> dict[str, JsonValue] | None:
    if not isinstance(value, dict):
        return None
    string_key_items = [(key, item) for key, item in value.items() if isinstance(key, str)]
    if len(string_key_items) != len(value):
        return None
    return dict(string_key_items)
