from __future__ import annotations as _annotations

import os
from collections.abc import Callable
from pathlib import Path

from acp.schema import ModelInfo, SessionMode
from codex_auth_helper import create_codex_chat_openai
from langchain.agents import create_agent
from langchain_acp import (
    AcpSessionContext,
    AdapterConfig,
    CompiledAgentGraph,
    FileSystemProjectionMap,
    MemorySessionStore,
    run_acp,
)

__all__ = (
    "AVAILABLE_MODELS",
    "AVAILABLE_MODES",
    "MODEL_NAME",
    "WORKSPACE_ROOT",
    "config",
    "codex_instructions",
    "describe_workspace_surface",
    "graph",
    "graph_from_session",
    "list_workspace_files",
    "main",
    "read_workspace_note",
    "write_workspace_note",
)

WORKSPACE_ROOT = Path.cwd() / ".workspace-graph"
_READ_TOOL = "read_workspace_note"
_WRITE_TOOL = "write_workspace_note"
_SESSION_ROOT_NAME = ".workspace-graph"
MODEL_NAME = os.getenv("CODEX_MODEL", "gpt-5.4")
AVAILABLE_MODELS = (
    ModelInfo(model_id="gpt-5.4-mini", name="GPT-5.4 Mini"),
    ModelInfo(model_id=MODEL_NAME, name=f"Codex {MODEL_NAME}"),
)
AVAILABLE_MODES = (
    SessionMode(id="ask", name="Ask", description="Inspect the workspace and answer questions."),
    SessionMode(id="edit", name="Edit", description="Make direct workspace changes."),
    SessionMode(id="plan", name="Plan", description="Plan before making changes."),
)


def codex_instructions(*, mode_id: str) -> str:
    """Return the Codex Responses instructions used by the workspace graph."""

    base = (
        "You are a careful workspace assistant operating inside a small demo workspace. "
        "Prefer reading files before changing them, keep edits focused, "
        "and describe exactly which workspace files you used."
    )
    if mode_id == "edit":
        return f"{base} When a change is needed, write the smallest viable file update."
    if mode_id == "plan":
        return f"{base} Start with a short implementation plan before proposing edits."
    return base


def _ensure_workspace(root: Path | None = None) -> Path:
    if root is None:
        root = WORKSPACE_ROOT
    root.mkdir(parents=True, exist_ok=True)
    readme_path = root / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            "# Workspace Graph Demo\n\n"
            "This seeded file lets ACP render a read diff through the LangChain example.\n",
            encoding="utf-8",
        )
    return root


def _resolve_workspace_path(path: str, *, root: Path | None = None) -> Path:
    if root is None:
        root = WORKSPACE_ROOT
    workspace_root = _ensure_workspace(root).resolve()
    candidate = (workspace_root / path).resolve()
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("Path must stay inside the workspace graph demo directory.") from exc
    return candidate


def _write_workspace_note(root: Path, path: str, content: str) -> str:
    note_path = _resolve_workspace_path(path, root=root)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")
    return f"Wrote `{note_path.relative_to(root).as_posix()}`."


def _workspace_surface_summary() -> str:
    return "\n".join(
        (
            "Workspace graph features:",
            f"- Codex-backed ChatOpenAI model via `codex-auth-helper` (`{MODEL_NAME}`)",
            "- module-level `graph` for direct `acpkit run ...:graph` exposure",
            "- session-aware `graph_from_session(...)` for per-session graph construction",
            "- file read and write projection through `FileSystemProjectionMap`",
            "- a seeded workspace that keeps ACP rendering deterministic",
        )
    )


def list_workspace_files() -> str:
    """List seeded workspace files that the demo graph can read."""

    root = _ensure_workspace()
    files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    return "\n".join(files)


def describe_workspace_surface() -> str:
    """Summarize the ACP-facing features exposed by the workspace graph example."""

    return _workspace_surface_summary()


def read_workspace_note(path: str) -> str:
    """Read a workspace note and return its text content."""

    note_path = _resolve_workspace_path(path)
    if not note_path.exists():
        raise ValueError(f"File not found: {path}")
    return note_path.read_text(encoding="utf-8")


def write_workspace_note(path: str, content: str) -> str:
    """Write a workspace note and return the saved relative path."""

    root = _ensure_workspace()
    return _write_workspace_note(root, path, content)


def _session_workspace_root(session: AcpSessionContext) -> Path:
    return session.cwd.resolve() / _SESSION_ROOT_NAME


def _bind_workspace_tools(root: Path) -> tuple[Callable[..., str], ...]:
    def _describe_workspace_surface() -> str:
        return _workspace_surface_summary()

    _describe_workspace_surface.__name__ = "describe_workspace_surface"
    _describe_workspace_surface.__doc__ = describe_workspace_surface.__doc__

    def _list_workspace_files() -> str:
        files = sorted(
            path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
        )
        return "\n".join(files)

    _list_workspace_files.__name__ = "list_workspace_files"
    _list_workspace_files.__doc__ = list_workspace_files.__doc__

    def _read_workspace_note(path: str) -> str:
        note_path = _resolve_workspace_path(path, root=root)
        if not note_path.exists():
            raise ValueError(f"File not found: {path}")
        return note_path.read_text(encoding="utf-8")

    _read_workspace_note.__name__ = _READ_TOOL
    _read_workspace_note.__doc__ = read_workspace_note.__doc__

    def _write_workspace_note_tool(path: str, content: str) -> str:
        return _write_workspace_note(root, path, content)

    _write_workspace_note_tool.__name__ = _WRITE_TOOL
    _write_workspace_note_tool.__doc__ = write_workspace_note.__doc__
    return (
        _describe_workspace_surface,
        _list_workspace_files,
        _read_workspace_note,
        _write_workspace_note_tool,
    )


def _build_graph(
    root: Path,
    *,
    name: str,
    model_name: str,
    mode_id: str,
) -> CompiledAgentGraph:
    _ensure_workspace(root)
    return create_agent(
        model=create_codex_chat_openai(
            model_name,
            instructions=codex_instructions(mode_id=mode_id),
        ),
        tools=list(_bind_workspace_tools(root)),
        name=name,
    )


def graph_from_session(session: AcpSessionContext) -> CompiledAgentGraph:
    root = _ensure_workspace(_session_workspace_root(session)).resolve()
    model_name = session.session_model_id or config.default_model_id or MODEL_NAME
    mode_id = session.session_mode_id or config.default_mode_id or "ask"
    return _build_graph(
        root,
        name=f"workspace-{mode_id}-{session.cwd.name}",
        model_name=model_name,
        mode_id=mode_id,
    )


graph = _build_graph(
    _ensure_workspace().resolve(),
    name="workspace-graph",
    model_name=MODEL_NAME,
    mode_id="ask",
)

config = AdapterConfig(
    available_models=list(AVAILABLE_MODELS),
    available_modes=list(AVAILABLE_MODES),
    default_model_id=AVAILABLE_MODELS[0].model_id,
    default_mode_id=AVAILABLE_MODES[0].id,
    session_store=MemorySessionStore(),
    projection_maps=[
        FileSystemProjectionMap(
            read_tool_names=frozenset({_READ_TOOL}),
            write_tool_names=frozenset({_WRITE_TOOL}),
        ),
    ],
)


def main() -> None:
    _ensure_workspace()
    run_acp(graph_factory=graph_from_session, config=config)


if __name__ == "__main__":
    main()
