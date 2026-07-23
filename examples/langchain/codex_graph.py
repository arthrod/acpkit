from __future__ import annotations as _annotations

import os
from collections.abc import Callable
from pathlib import Path

from acp.schema import SessionMode
from codex_auth_helper import create_codex_chat_openai
from langchain.agents import create_agent
from langchain_acp import (
    AcpSessionContext,
    AdapterConfig,
    AdapterModel,
    CompiledAgentGraph,
    FileSessionStore,
    create_acp_agent,
    run_acp,
)

__all__ = (
    "AVAILABLE_MODELS",
    "AVAILABLE_MODES",
    "MODEL_NAME",
    "acp_agent",
    "build_graph",
    "codex_instructions",
    "config",
    "describe_codex_surface",
    "graph",
    "graph_from_session",
    "main",
)

MODEL_NAME = os.getenv("CODEX_MODEL", "gpt-5.4")
_DEMO_ROOT = Path("agent_demos")
_SESSION_STORE_ROOT = (
    Path(os.getenv("ACP_EXAMPLE_SESSION_DIR", str(_DEMO_ROOT / "acp-sessions")))
    .expanduser()
    .resolve()
    / "langchain-codex"
)
AVAILABLE_MODELS = (
    AdapterModel(model_id="gpt-5.4-mini", name="GPT-5.4 Mini"),
    AdapterModel(model_id=MODEL_NAME, name=f"Codex {MODEL_NAME}"),
)
AVAILABLE_MODES = (
    SessionMode(id="ask", name="Ask", description="General question answering mode."),
    SessionMode(id="edit", name="Edit", description="Make focused workspace edits."),
    SessionMode(id="plan", name="Plan", description="Plan first, then suggest next steps."),
)


def codex_instructions(*, mode_id: str) -> str:
    """Return the Codex Responses instructions used by this example graph."""
    base = (
        "You are a precise workspace assistant. "
        "Use the available tools when they help, keep answers concise, "
        "and explain concrete file or project observations instead of guessing."
    )
    if mode_id == "edit":
        return f"{base} Prefer concrete edits and summarize the changed files."
    if mode_id == "plan":
        return f"{base} Start with a short plan before proposing changes."
    return base


def describe_codex_surface() -> str:
    """Summarize the Codex-backed LangChain example surface."""
    return "\n".join(
        (
            "Codex graph features:",
            "- LangChain ChatOpenAI wired through codex-auth-helper",
            "- OpenAI Responses API transport through local Codex auth state",
            "- ready for `langchain-acp` exposure through `run_acp(graph=...)`",
        ),
    )


def _tools() -> tuple[Callable[[], str], ...]:
    return (describe_codex_surface,)


def _resolved_model_name(session: AcpSessionContext | None = None) -> str:
    if session is None or not session.session_model_id:
        return MODEL_NAME
    return session.session_model_id


def _resolved_mode_id(session: AcpSessionContext | None = None) -> str:
    if session is None or not session.session_mode_id:
        return "ask"
    return session.session_mode_id


def build_graph(
    *,
    model_name: str | None = None,
    mode_id: str = "ask",
    graph_name: str = "codex-graph",
) -> CompiledAgentGraph:
    return create_agent(
        model=create_codex_chat_openai(
            model_name or MODEL_NAME,
            instructions=codex_instructions(mode_id=mode_id),
        ),
        tools=list(_tools()),
        name=graph_name,
    )


def graph_from_session(session: AcpSessionContext) -> CompiledAgentGraph:
    model_name = _resolved_model_name(session)
    mode_id = _resolved_mode_id(session)
    return build_graph(
        model_name=model_name,
        mode_id=mode_id,
        graph_name=f"codex-{mode_id}-{session.cwd.name}",
    )


graph = build_graph(model_name=MODEL_NAME, mode_id="ask")


config = AdapterConfig(
    available_models=list(AVAILABLE_MODELS),
    available_modes=list(AVAILABLE_MODES),
    default_model_id=AVAILABLE_MODELS[0].model_id,
    default_mode_id=AVAILABLE_MODES[0].id,
    session_store=FileSessionStore(_SESSION_STORE_ROOT),
)
acp_agent = create_acp_agent(graph_factory=graph_from_session, config=config)


def main() -> None:
    run_acp(graph_factory=graph_from_session, config=config)


if __name__ == "__main__":
    main()
