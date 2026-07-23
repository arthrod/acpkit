from __future__ import annotations as _annotations

import os
from pathlib import Path
from typing import Final

from pydantic_acp import (
    AcpSessionContext,
    AdapterConfig,
    AgentBridgeBuilder,
    CapabilityBridge,
    FileSessionStore,
    SessionMcpBridge,
    create_acp_agent,
    run_acp,
)
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

__all__ = ("acp_agent", "agent_factory", "config", "main")

_AGENT_NAME: Final[str] = "session-mcp-agent"
_DEMO_ROOT: Final[Path] = Path("agent_demos")
_SESSION_STORE_ROOT: Final[Path] = (
    Path(os.getenv("ACP_EXAMPLE_SESSION_DIR", str(_DEMO_ROOT / "acp-sessions")))
    .expanduser()
    .resolve()
    / "pydantic-session-mcp"
)
_INSTRUCTIONS: Final[str] = (
    "You are an ACP Kit session MCP demo agent. If the ACP client attaches MCP servers "
    "during session creation, use their tools through the session MCP bridge. Use "
    "`/mcp-servers` to inspect attached servers and `/tools` to inspect visible tools."
)
_BRIDGES: Final[tuple[CapabilityBridge, ...]] = (
    SessionMcpBridge(
        include_instructions=True,
        include_return_schema=True,
        tool_name_prefixes=frozenset({"docs_", "repo_"}),
    ),
)


def _model() -> str | TestModel:
    configured_model = os.getenv("ACP_SESSION_MCP_MODEL", "").strip()
    if configured_model:
        return configured_model
    return TestModel(custom_output_text="Session MCP bridge ready.")


def agent_factory(session: AcpSessionContext) -> Agent[None, str]:
    bridge_contributions = AgentBridgeBuilder(
        session=session,
        capability_bridges=_BRIDGES,
    ).build()
    return Agent(
        _model(),
        name=_AGENT_NAME,
        capabilities=bridge_contributions.capabilities,
        instructions=_INSTRUCTIONS,
    )


config = AdapterConfig(
    agent_name=_AGENT_NAME,
    agent_title="Session MCP Agent",
    session_store=FileSessionStore(_SESSION_STORE_ROOT),
    capability_bridges=_BRIDGES,
)
acp_agent = create_acp_agent(agent_factory=agent_factory, config=config)


def main() -> None:
    run_acp(agent_factory=agent_factory, config=config)


if __name__ == "__main__":  # pragma: no cover
    main()
