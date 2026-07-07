from __future__ import annotations as _annotations

import importlib
import runpy
import sys
from itertools import cycle
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_acp import AcpSessionContext
from langchain_acp.session import utc_now
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


def _fake_codex_model() -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=cycle([AIMessage(content="codex-ready")]))


def _load_example_module(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
) -> Any:
    import codex_auth_helper

    monkeypatch.setattr(
        codex_auth_helper,
        "create_codex_chat_openai",
        lambda _model_name, **_kwargs: _fake_codex_model(),
    )
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _run_example_module_as_main(module_name: str) -> dict[str, Any]:
    sys.modules.pop(module_name, None)
    return runpy.run_module(module_name, run_name="__main__")


def test_langchain_example_main_dispatches_run_acp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_graph = _load_example_module(monkeypatch, "examples.langchain.workspace_graph")
    captured: list[tuple[Any, Any]] = []

    def fake_run_acp(*, graph_factory: Any, config: Any) -> None:
        captured.append((graph_factory, config))

    monkeypatch.setattr(workspace_graph, "run_acp", fake_run_acp)
    workspace_graph.main()

    assert captured == [(workspace_graph.graph_from_session, workspace_graph.config)]


def test_codex_langchain_example_builds_graph_from_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_graph = _load_example_module(monkeypatch, "examples.langchain.codex_graph")
    captured: dict[str, Any] = {}

    def fake_create_codex_chat_openai(model_name: str, *, instructions: str) -> str:
        captured["model_name"] = model_name
        captured["instructions"] = instructions
        return "codex-model"

    def fake_create_agent(*, model: Any, tools: list[Any], name: str) -> object:
        captured["model"] = model
        captured["tools"] = tools
        captured["name"] = name
        return object()

    monkeypatch.setattr(codex_graph, "create_codex_chat_openai", fake_create_codex_chat_openai)
    monkeypatch.setattr(codex_graph, "create_agent", fake_create_agent)

    graph = codex_graph.build_graph()

    assert graph is not None
    assert captured["model_name"] == codex_graph.MODEL_NAME
    assert captured["model"] == "codex-model"
    assert captured["name"] == "codex-graph"
    assert "workspace assistant" in captured["instructions"]
    assert [tool.__name__ for tool in captured["tools"]] == ["describe_codex_surface"]
    assert "Codex graph features:" in codex_graph.describe_codex_surface()
    assert codex_graph.config.available_models
    assert codex_graph.config.available_modes


def test_codex_langchain_example_main_dispatches_run_acp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_graph = _load_example_module(monkeypatch, "examples.langchain.codex_graph")
    captured: list[tuple[Any, Any]] = []

    def fake_run_acp(*, graph_factory: Any, config: Any) -> None:
        captured.append((graph_factory, config))

    monkeypatch.setattr(codex_graph, "run_acp", fake_run_acp)

    codex_graph.main()

    assert captured == [(codex_graph.graph_from_session, codex_graph.config)]


def test_codex_langchain_example_module_runs_as_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    import codex_auth_helper
    import langchain.agents
    import langchain_acp

    monkeypatch.setattr(
        codex_auth_helper,
        "create_codex_chat_openai",
        lambda _, **_kwargs: "codex-model",
    )
    monkeypatch.setattr(
        langchain.agents,
        "create_agent",
        lambda *, model, tools, name: {
            "model": model,
            "tools": tools,
            "name": name,
        },
    )

    def fake_run_acp(*, graph_factory: Any, config: Any) -> None:
        observed["call"] = (graph_factory, config)

    monkeypatch.setattr(langchain_acp, "run_acp", fake_run_acp)

    _run_example_module_as_main("examples.langchain.codex_graph")

    graph_factory, config = observed["call"]
    session = AcpSessionContext(
        session_id="codex-example",
        cwd=Path.cwd(),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    graph = graph_factory(session)
    assert graph["model"] == "codex-model"
    assert graph["name"].startswith("codex-")
    assert config is not None


def test_codex_langchain_example_graph_factory_uses_session_model_and_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_graph = _load_example_module(monkeypatch, "examples.langchain.codex_graph")
    captured: dict[str, Any] = {}

    def fake_create_codex_chat_openai(model_name: str, *, instructions: str) -> str:
        captured["model_name"] = model_name
        captured["instructions"] = instructions
        return "codex-model"

    def fake_create_agent(*, model: Any, tools: list[Any], name: str) -> object:
        captured["model"] = model
        captured["name"] = name
        captured["tools"] = tools
        return {"model": model, "name": name}

    monkeypatch.setattr(codex_graph, "create_codex_chat_openai", fake_create_codex_chat_openai)
    monkeypatch.setattr(codex_graph, "create_agent", fake_create_agent)

    session = AcpSessionContext(
        session_id="codex-session",
        cwd=tmp_path,
        created_at=utc_now(),
        updated_at=utc_now(),
        session_model_id="gpt-5.4",
        session_mode_id="plan",
    )
    graph = codex_graph.graph_from_session(session)

    assert graph == {"model": "codex-model", "name": f"codex-plan-{tmp_path.name}"}
    assert captured["model_name"] == "gpt-5.4"
    assert "short plan" in captured["instructions"]


def test_codex_langchain_example_edit_mode_instructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_graph = _load_example_module(monkeypatch, "examples.langchain.codex_graph")

    assert "changed files" in codex_graph.codex_instructions(mode_id="edit")


def test_langchain_example_workspace_helpers_cover_seeded_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_graph = _load_example_module(monkeypatch, "examples.langchain.workspace_graph")
    root = tmp_path / ".workspace-graph"
    monkeypatch.setattr(workspace_graph, "WORKSPACE_ROOT", root)

    workspace_graph._ensure_workspace()

    assert workspace_graph.list_workspace_files() == "README.md"
    assert "session-aware `graph_from_session(...)`" in workspace_graph.describe_workspace_surface()
    assert "Workspace Graph Demo" in workspace_graph.read_workspace_note("README.md")
    assert workspace_graph.write_workspace_note("scratch.txt", "# Hello") == "Wrote `scratch.txt`."
    assert workspace_graph.list_workspace_files() == "README.md\nscratch.txt"
    assert workspace_graph.config.available_models
    assert workspace_graph.config.available_modes

    with pytest.raises(ValueError, match="workspace graph demo directory"):
        workspace_graph._resolve_workspace_path("../escape.md")

    with pytest.raises(ValueError, match="File not found"):
        workspace_graph.read_workspace_note("missing.md")

    assert workspace_graph.config.projection_maps


def test_langchain_example_workspace_graph_factory_uses_session_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_graph = _load_example_module(monkeypatch, "examples.langchain.workspace_graph")
    session_root = tmp_path / "remote-workspace"
    session_root.mkdir(parents=True, exist_ok=True)
    session = AcpSessionContext(
        session_id="workspace-example",
        cwd=session_root,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    graph = workspace_graph.graph_from_session(session)

    assert graph is not None
    seeded_root = session_root / ".workspace-graph"
    assert (seeded_root / "README.md").exists()


def test_langchain_example_workspace_graph_factory_uses_session_model_and_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_graph = _load_example_module(monkeypatch, "examples.langchain.workspace_graph")
    captured: dict[str, Any] = {}

    def fake_create_codex_chat_openai(model_name: str, *, instructions: str) -> str:
        captured["model_name"] = model_name
        captured["instructions"] = instructions
        return "workspace-model"

    def fake_create_agent(*, model: Any, tools: list[Any], name: str) -> object:
        captured["model"] = model
        captured["name"] = name
        captured["tools"] = tools
        return {"model": model, "name": name}

    monkeypatch.setattr(workspace_graph, "create_codex_chat_openai", fake_create_codex_chat_openai)
    monkeypatch.setattr(workspace_graph, "create_agent", fake_create_agent)

    session = AcpSessionContext(
        session_id="workspace-session",
        cwd=tmp_path,
        created_at=utc_now(),
        updated_at=utc_now(),
        session_model_id="gpt-5.4",
        session_mode_id="edit",
    )
    graph = workspace_graph.graph_from_session(session)

    assert graph == {"model": "workspace-model", "name": f"workspace-edit-{tmp_path.name}"}
    assert captured["model_name"] == "gpt-5.4"
    assert "smallest viable file update" in captured["instructions"]


def test_langchain_example_workspace_plan_mode_instructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_graph = _load_example_module(monkeypatch, "examples.langchain.workspace_graph")

    assert "short implementation plan" in workspace_graph.codex_instructions(mode_id="plan")


def test_langchain_example_workspace_bound_tools_cover_private_closures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_graph = _load_example_module(monkeypatch, "examples.langchain.workspace_graph")
    root = tmp_path / ".workspace-graph"
    root.mkdir(parents=True, exist_ok=True)
    tools = {tool.__name__: tool for tool in workspace_graph._bind_workspace_tools(root)}

    assert tools["describe_workspace_surface"]() == workspace_graph.describe_workspace_surface()
    assert tools["list_workspace_files"]() == ""
    assert tools["read_workspace_note"].__name__ == "read_workspace_note"
    assert tools["write_workspace_note"].__name__ == "write_workspace_note"

    assert tools["write_workspace_note"]("note.md", "# Demo") == "Wrote `note.md`."
    assert tools["list_workspace_files"]() == "README.md\nnote.md"
    assert tools["read_workspace_note"]("note.md") == "# Demo"

    with pytest.raises(ValueError, match="File not found"):
        tools["read_workspace_note"]("missing.md")


def test_langchain_example_workspace_module_runs_as_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    import langchain_acp

    def fake_run_acp(*, graph_factory: Any, config: Any) -> None:
        observed["call"] = (graph_factory, config)

    monkeypatch.setattr(langchain_acp, "run_acp", fake_run_acp)
    import codex_auth_helper

    monkeypatch.setattr(
        codex_auth_helper,
        "create_codex_chat_openai",
        lambda _model_name, **_kwargs: _fake_codex_model(),
    )

    _run_example_module_as_main("examples.langchain.workspace_graph")

    graph_factory, config = observed["call"]
    assert graph_factory.__name__ == "graph_from_session"
    assert config is not None


def test_deepagents_example_main_dispatches_run_acp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deepagents_graph = _load_example_module(monkeypatch, "examples.langchain.deepagents_graph")
    captured: list[tuple[Any, Any]] = []

    def fake_run_acp(*, graph_factory: Any, config: Any) -> None:
        captured.append((graph_factory, config))

    monkeypatch.setattr(deepagents_graph, "run_acp", fake_run_acp)
    deepagents_graph.main()

    assert captured == [(deepagents_graph.graph_from_session, deepagents_graph.config)]


def test_deepagents_example_workspace_helpers_cover_seeded_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deepagents_graph = _load_example_module(monkeypatch, "examples.langchain.deepagents_graph")
    root = tmp_path / ".deepagents-graph"
    monkeypatch.setattr(deepagents_graph, "WORKSPACE_ROOT", root)

    deepagents_graph._ensure_workspace()

    assert deepagents_graph.list_workspace_files() == "brief.md\nnotes.md"
    assert "DeepAgents Demo" in deepagents_graph.read_file("brief.md")
    assert (
        deepagents_graph.write_file("itinerary.md", "# Trip")
        == "Mock write accepted for itinerary.md"
    )
    assert deepagents_graph.list_workspace_files() == "brief.md\nnotes.md"
    assert deepagents_graph.config.available_models
    assert deepagents_graph.config.available_modes
    assert (
        deepagents_graph._resolve_workspace_path("itinerary.md", root=root)
        == (root / "itinerary.md").resolve()
    )
    assert (
        deepagents_graph._resolve_workspace_path(".deepagents-graph/itinerary.md", root=root)
        == (root / "itinerary.md").resolve()
    )
    assert (
        deepagents_graph._resolve_workspace_path(str((root / "itinerary.md").resolve()), root=root)
        == (root / "itinerary.md").resolve()
    )
    assert (
        deepagents_graph._resolve_workspace_path(
            str((root.parent / "itinerary.md").resolve()),
            root=root,
        )
        == (root / "itinerary.md").resolve()
    )

    with pytest.raises(ValueError, match="DeepAgents example workspace"):
        deepagents_graph._resolve_workspace_path("../escape.md")

    with pytest.raises(ValueError, match="File not found"):
        deepagents_graph.read_file("missing.md")

    assert deepagents_graph.config.projection_maps


def test_deepagents_example_helper_edges_cover_remaining_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deepagents_graph = _load_example_module(monkeypatch, "examples.langchain.deepagents_graph")
    root = tmp_path / ".deepagents-graph"
    monkeypatch.setattr(deepagents_graph, "WORKSPACE_ROOT", root)

    assert "direct file edits" in deepagents_graph.codex_instructions(mode_id="edit")

    outside_root = tmp_path / "outside"
    outside_root.mkdir(parents=True, exist_ok=True)
    outside_child = outside_root / "escape.md"
    resolved = deepagents_graph._resolve_workspace_path(str(outside_child.resolve()), root=root)
    assert resolved == (root / "outside" / "escape.md").resolve()

    nested_prefixed = root.parent / root.name / "nested" / "note.md"
    normalized = deepagents_graph._resolve_workspace_path(str(nested_prefixed.resolve()), root=root)
    assert normalized == (root / "nested" / "note.md").resolve()

    external_absolute = Path("/tmp") / "deepagents-escape.md"
    with pytest.raises(ValueError, match="DeepAgents example workspace"):
        deepagents_graph._resolve_workspace_path(str(external_absolute.resolve()), root=root)

    with pytest.raises(ValueError, match="mocked workspace file"):
        deepagents_graph._normalized_mock_path("")


def test_deepagents_example_graph_factory_requires_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deepagents_graph = _load_example_module(monkeypatch, "examples.langchain.deepagents_graph")
    session = AcpSessionContext(
        session_id="example-session",
        cwd=Path.cwd(),
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    monkeypatch.setattr(deepagents_graph, "_deepagents_available", lambda: False)

    with pytest.raises(RuntimeError, match="langchain-acp\\[deepagents\\]"):
        deepagents_graph.graph_from_session(session)


def test_deepagents_example_graph_factory_builds_graph_from_lazy_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deepagents_graph = _load_example_module(monkeypatch, "examples.langchain.deepagents_graph")
    root = tmp_path / ".deepagents-graph"
    monkeypatch.setattr(deepagents_graph, "WORKSPACE_ROOT", root)
    monkeypatch.setattr(deepagents_graph, "_deepagents_available", lambda: True)

    captured: dict[str, Any] = {}

    def fake_create_deep_agent(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setitem(
        sys.modules,
        "deepagents",
        cast("Any", SimpleNamespace(create_deep_agent=fake_create_deep_agent)),
    )

    session = AcpSessionContext(
        session_id="example-session",
        cwd=root,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    graph = deepagents_graph.graph_from_session(session)

    assert graph is not None
    assert captured["interrupt_on"] == {"write_file": True}
    assert captured["name"] == "deepagents-ask-.deepagents-graph"
    tool_names = {tool.__name__ for tool in cast("list[Any]", captured["tools"])}
    assert {
        "list_workspace_files",
        "read_file",
        "write_file",
        "acp_get_plan",
        "acp_set_plan",
        "acp_update_plan_entry",
        "acp_mark_plan_done",
    } <= tool_names


def test_deepagents_example_graph_factory_builds_graph_when_dependency_is_mocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deepagents_graph = _load_example_module(monkeypatch, "examples.langchain.deepagents_graph")
    fake_graph = object()
    captured: dict[str, Any] = {}

    def fake_create_deep_agent(**kwargs: Any) -> object:
        captured.update(kwargs)
        return fake_graph

    monkeypatch.setattr(deepagents_graph, "_deepagents_available", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "deepagents",
        cast("Any", SimpleNamespace(create_deep_agent=fake_create_deep_agent)),
    )

    session = AcpSessionContext(
        session_id="example-session",
        cwd=tmp_path,
        created_at=utc_now(),
        updated_at=utc_now(),
        session_model_id="gpt-5.4",
        session_mode_id="plan",
    )

    assert deepagents_graph.graph_from_session(session) is fake_graph
    tool_names = {tool.__name__ for tool in cast("list[Any]", captured["tools"])}
    assert {
        "list_workspace_files",
        "read_file",
        "write_file",
        "acp_get_plan",
        "acp_set_plan",
        "acp_update_plan_entry",
        "acp_mark_plan_done",
    } <= tool_names
    assert captured["name"] == f"deepagents-plan-{tmp_path.name}"


def test_deepagents_example_bound_tools_use_session_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deepagents_graph = _load_example_module(monkeypatch, "examples.langchain.deepagents_graph")
    session_root = tmp_path / "remote-workspace"
    session_root.mkdir(parents=True, exist_ok=True)
    bound_root = session_root / ".deepagents-graph"
    tools = {tool.__name__: tool for tool in deepagents_graph._bind_workspace_tools(bound_root)}

    assert tools["list_workspace_files"]() == "brief.md\nnotes.md"
    assert tools["write_file"]("notes.md", "# Deep") == "Mock write accepted for notes.md"
    assert tools["list_workspace_files"]() == "brief.md\nnotes.md"
    assert "Mock Notes" in tools["read_file"]("notes.md")

    with pytest.raises(ValueError, match="File not found"):
        tools["read_file"]("missing.md")


def test_deepagents_example_seed_session_and_module_run_as_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deepagents_graph = _load_example_module(monkeypatch, "examples.langchain.deepagents_graph")
    root = tmp_path / ".deepagents-graph"
    monkeypatch.setattr(deepagents_graph, "WORKSPACE_ROOT", root)

    session = deepagents_graph._seed_session()
    assert session.session_id == "deepagents-example"
    assert session.cwd == root.resolve()

    observed: dict[str, Any] = {}

    import langchain_acp

    def fake_run_acp(*, graph_factory: Any, config: Any) -> None:
        observed["call"] = (graph_factory, config)

    monkeypatch.setattr(langchain_acp, "run_acp", fake_run_acp)
    import codex_auth_helper

    monkeypatch.setattr(
        codex_auth_helper,
        "create_codex_chat_openai",
        lambda _model_name, **_kwargs: _fake_codex_model(),
    )
    _run_example_module_as_main("examples.langchain.deepagents_graph")

    graph_factory, config = observed["call"]
    assert graph_factory.__name__ == "graph_from_session"
    assert config is not None
