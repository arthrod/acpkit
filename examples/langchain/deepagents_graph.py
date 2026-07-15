from __future__ import annotations as _annotations

import os
from collections.abc import Callable, Sequence
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from acp.schema import SessionMode
from codex_auth_helper import create_codex_chat_openai
from langchain_acp import (
    AcpSessionContext,
    AdapterConfig,
    AdapterModel,
    DeepAgentsCompatibilityBridge,
    DeepAgentsProjectionMap,
    FileSessionStore,
    create_acp_agent,
    native_plan_tools,
    run_acp,
)
from langchain_acp.session import utc_now

if TYPE_CHECKING:
    from langchain_acp import CompiledAgentGraph
    from langchain_core.tools import BaseTool

DeepAgentTool: TypeAlias = "BaseTool | Callable[..., Any] | dict[str, Any]"

__all__ = (
    "AVAILABLE_MODELS",
    "AVAILABLE_MODES",
    "MODEL_NAME",
    "WORKSPACE_ROOT",
    "acp_agent",
    "codex_instructions",
    "config",
    "graph",
    "graph_from_session",
    "list_workspace_files",
    "main",
    "read_file",
    "write_file",
)

_DEMO_ROOT = Path("agent_demos")
WORKSPACE_ROOT = Path.cwd() / _DEMO_ROOT / "deepagents-graph"
MODEL_NAME = os.getenv("CODEX_MODEL", "gpt-5.4")
_SESSION_ROOT = _DEMO_ROOT / "deepagents-graph"
_SESSION_STORE_ROOT = (
    Path(os.getenv("ACP_EXAMPLE_SESSION_DIR", str(_DEMO_ROOT / "acp-sessions")))
    .expanduser()
    .resolve()
    / "langchain-deepagents"
)
MOCK_WORKSPACE_FILES = {
    "brief.md": (
        "# DeepAgents Demo\n\nThis is a mocked workspace file used by the DeepAgents example.\n"
    ),
    "notes.md": (
        "# Mock Notes\n\n"
        "- This example uses fixed filesystem tool outputs.\n"
        "- No real workspace mutation happens here.\n"
    ),
}
AVAILABLE_MODELS = (
    AdapterModel(model_id="gpt-5.4-mini", name="GPT-5.4 Mini"),
    AdapterModel(model_id=MODEL_NAME, name="GPT-5.4"),
)
AVAILABLE_MODES = (
    SessionMode(id="ask", name="Ask", description="Inspect the workspace and answer questions."),
    SessionMode(id="edit", name="Edit", description="Make direct workspace changes."),
    SessionMode(id="plan", name="Plan", description="Plan before applying changes."),
)
DEFAULT_MODEL_ID = AVAILABLE_MODELS[0].model_id
DEFAULT_MODE_ID = AVAILABLE_MODES[0].id


def codex_instructions(*, mode_id: str) -> str:
    """Return the Codex Responses instructions used by the DeepAgents example."""
    base = (
        "You are a workspace agent that can inspect and update files in the current demo workspace. "
        "Use tools for concrete file work, keep changes scoped, and summarize what changed."
    )
    if mode_id == "edit":
        return f"{base} Prefer direct file edits when the user asks for changes."
    if mode_id == "plan":
        return f"{base} Begin with a short plan before making any edits."
    return base


def _deepagents_available() -> bool:
    return find_spec("deepagents") is not None


def _ensure_workspace(root: Path | None = None) -> Path:
    if root is None:
        root = WORKSPACE_ROOT
    root.mkdir(parents=True, exist_ok=True)
    brief_path = root / "brief.md"
    if not brief_path.exists():
        brief_path.write_text(
            "# DeepAgents Demo\n\n"
            "This seeded file exists so ACP can render read and write projections.\n",
            encoding="utf-8",
        )
    return root


def _resolve_workspace_path(path: str, *, root: Path | None = None) -> Path:
    if root is None:
        root = WORKSPACE_ROOT
    workspace_root = _ensure_workspace(root).resolve()
    workspace_parent = workspace_root.parent
    requested_path = Path(path)
    if requested_path.is_absolute():
        absolute_candidate = requested_path.resolve()
        try:
            relative_to_workspace = absolute_candidate.relative_to(workspace_root)
        except ValueError:
            try:
                relative_to_parent = absolute_candidate.relative_to(workspace_parent)
            except ValueError:
                candidate = absolute_candidate
            else:
                relative_to_parent = Path(
                    *(
                        relative_to_parent.parts[1:]
                        if relative_to_parent.parts
                        and relative_to_parent.parts[0] == workspace_root.name
                        else relative_to_parent.parts
                    ),
                )
                candidate = (workspace_root / relative_to_parent).resolve()
        else:
            candidate = (workspace_root / relative_to_workspace).resolve()
    else:
        relative_path = requested_path
        if requested_path.parts and requested_path.parts[0] == workspace_root.name:
            relative_path = Path(*requested_path.parts[1:])
        candidate = (workspace_root / relative_path).resolve()
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("Path must stay inside the DeepAgents example workspace.") from exc
    return candidate


def _normalized_mock_path(path: str) -> str:
    normalized = Path(path).name.strip()
    if not normalized:
        raise ValueError("Path must reference a mocked workspace file.")
    return normalized


def list_workspace_files() -> str:
    """List mocked workspace files exposed by the DeepAgents example."""
    return "\n".join(sorted(MOCK_WORKSPACE_FILES))


def read_file(path: str) -> str:
    """Read a mocked file from the DeepAgents example workspace."""
    normalized = _normalized_mock_path(path)
    content = MOCK_WORKSPACE_FILES.get(normalized)
    if content is None:
        raise ValueError(f"File not found: {path}")
    return content


def write_file(path: str, content: str) -> str:
    """Pretend to write a file in the DeepAgents example workspace."""
    normalized = _normalized_mock_path(path)
    del content
    return f"Mock write accepted for {normalized}"


def _session_workspace_root(session: AcpSessionContext) -> Path:
    return session.cwd.resolve() / _SESSION_ROOT


def _bind_workspace_tools(
    root: Path,
) -> tuple[Callable[[], str], Callable[[str], str], Callable[[str, str], str]]:
    del root

    def _list_workspace_files() -> str:
        return "\n".join(sorted(MOCK_WORKSPACE_FILES))

    _list_workspace_files.__name__ = "list_workspace_files"
    _list_workspace_files.__doc__ = list_workspace_files.__doc__

    def _read_file(path: str) -> str:
        normalized = _normalized_mock_path(path)
        content = MOCK_WORKSPACE_FILES.get(normalized)
        if content is None:
            raise ValueError(f"File not found: {path}")
        return content

    _read_file.__name__ = "read_file"
    _read_file.__doc__ = read_file.__doc__

    def _write_file(path: str, content: str) -> str:
        del content
        normalized = _normalized_mock_path(path)
        return f"Mock write accepted for {normalized}"

    _write_file.__name__ = "write_file"
    _write_file.__doc__ = write_file.__doc__
    return (_list_workspace_files, _read_file, _write_file)


def graph_from_session(session: AcpSessionContext) -> CompiledAgentGraph:
    if not _deepagents_available():
        raise RuntimeError(
            'Install the optional DeepAgents dependency first: uv add "langchain-acp[deepagents]"',
        )
    workspace_root = _ensure_workspace(_session_workspace_root(session)).resolve()
    model_name = session.session_model_id or DEFAULT_MODEL_ID or MODEL_NAME
    mode_id = session.session_mode_id or DEFAULT_MODE_ID or "ask"
    from deepagents import create_deep_agent

    tools: Sequence[DeepAgentTool] = [
        *_bind_workspace_tools(workspace_root),
        *cast("Sequence[DeepAgentTool]", native_plan_tools()),
    ]
    return create_deep_agent(
        model=create_codex_chat_openai(
            model_name,
            instructions=codex_instructions(mode_id=mode_id),
        ),
        tools=tools,
        interrupt_on={"write_file": True},
        name=f"deepagents-{mode_id}-{session.cwd.name}",
    )


def _seed_session() -> AcpSessionContext:
    root = _ensure_workspace().resolve()
    timestamp = utc_now()
    return AcpSessionContext(
        session_id="deepagents-example",
        cwd=root,
        created_at=timestamp,
        updated_at=timestamp,
    )


graph = graph_from_session(_seed_session()) if _deepagents_available() else None

config = AdapterConfig(
    available_models=list(AVAILABLE_MODELS),
    available_modes=list(AVAILABLE_MODES),
    session_store=FileSessionStore(_SESSION_STORE_ROOT),
    capability_bridges=[DeepAgentsCompatibilityBridge()],
    default_model_id=DEFAULT_MODEL_ID,
    default_mode_id=DEFAULT_MODE_ID,
    default_plan_generation_type="tools",
    enable_plan_progress_tools=True,
    plan_id="deepagents-workspace-plan",
    plan_mode_id="plan",
    plan_update_mode="content",
    projection_maps=[DeepAgentsProjectionMap()],
)
acp_agent = create_acp_agent(graph_factory=graph_from_session, config=config)


def main() -> None:
    _ensure_workspace()
    run_acp(graph_factory=graph_from_session, config=config)


if __name__ == "__main__":
    main()
