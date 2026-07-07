from __future__ import annotations as _annotations

from ._version import __version__
from .client import RemoteClientConnection, connect_remote_agent
from .command import CommandOptions, run_remote_command_connection
from .config import (
    DEFAULT_HEALTH_PATH,
    ServerOptions,
    ServerPaths,
    TransportOptions,
    build_server_paths,
    normalize_mount_path,
)
from .metadata import ServerMetadata, TransportMetadata, build_server_metadata
from .proxy_agent import RemoteProxyAgent, connect_acp
from .server import (
    run_remote_agent_connection,
    serve_acp,
    serve_command,
    serve_remote_agent,
    serve_stdio_command,
)
from .stream import WebSocketStreamBridge, open_websocket_stream_bridge

__all__ = (
    "DEFAULT_HEALTH_PATH",
    "CommandOptions",
    "RemoteClientConnection",
    "RemoteProxyAgent",
    "ServerMetadata",
    "ServerOptions",
    "ServerPaths",
    "TransportMetadata",
    "TransportOptions",
    "WebSocketStreamBridge",
    "__version__",
    "build_server_metadata",
    "build_server_paths",
    "connect_acp",
    "connect_remote_agent",
    "normalize_mount_path",
    "open_websocket_stream_bridge",
    "run_remote_agent_connection",
    "run_remote_command_connection",
    "serve_acp",
    "serve_command",
    "serve_remote_agent",
    "serve_stdio_command",
)
