from __future__ import annotations as _annotations

import pytest
from acp import PROTOCOL_VERSION
from pydantic_acp import AdapterConfig, BlackBoxHarness, ClientHostContext, FileSessionStore
from pydantic_ai import Agent
from pydantic_ai.exceptions import ApprovalRequired
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext

from .support import (
    DemoConfigOptionsProvider,
    DemoModelsProvider,
    DemoModesProvider,
    DemoPlanProvider,
    DeniedOutcome,
    Path,
    ToolCallProgress,
    ToolCallStart,
)


async def test_black_box_harness_can_drive_approval_write_and_reload(tmp_path: Path) -> None:
    store = FileSessionStore(tmp_path / "sessions")

    def factory(session):
        host = ClientHostContext.from_session(
            client=session.client,
            session=session,
        )
        agent = Agent(
            TestModel(call_tools=["write_workspace_note"], custom_output_text="done"),
            deps_type=type(None),
        )

        @agent.tool
        async def write_workspace_note(ctx: RunContext[None], path: str, content: str) -> str:
            del ctx
            await host.filesystem.write_text_file(path, content)
            return "wrote"

        return agent

    harness = BlackBoxHarness.create(
        agent_factory=factory,
        config=AdapterConfig(session_store=store),
    )

    session = await harness.new_session(cwd=str(tmp_path))
    harness.queue_permission_selected("allow_once")
    prompt_response = await harness.prompt_text(
        "Write the workspace note.",
        session_id=session.session_id,
    )

    assert prompt_response.stop_reason == "end_turn"
    tool_starts = harness.updates_of_type(ToolCallStart, session_id=session.session_id)
    tool_progress = harness.updates_of_type(ToolCallProgress, session_id=session.session_id)
    assert any(update.title == "write_workspace_note" for update in tool_starts)
    assert any(update.status == "completed" for update in tool_progress)
    assert harness.client.write_calls == [(session.session_id, "a", "a")]
    assert harness.agent_messages(session_id=session.session_id) == ["done"]

    harness.clear_updates()
    loaded = await harness.load_session(
        cwd=str(tmp_path),
        session_id=session.session_id,
    )

    assert loaded is not None
    replayed_messages = harness.agent_messages(session_id=session.session_id)
    assert replayed_messages == ["done"]


async def test_black_box_harness_covers_initialize_mode_model_and_default_filters(
    tmp_path: Path,
) -> None:
    harness = BlackBoxHarness.create(
        agent=Agent(TestModel(custom_output_text="base")),
        config=AdapterConfig(
            models_provider=DemoModelsProvider(),
            modes_provider=DemoModesProvider(),
        ),
    )
    missing_session_harness = BlackBoxHarness.create(
        agent=Agent(TestModel(custom_output_text="unused"))
    )

    initialize_response = await harness.initialize()
    with pytest.raises(ValueError, match="No active session id"):
        missing_session_harness.require_session_id()

    assert missing_session_harness.current_mode_id() is None
    assert missing_session_harness.last_plan_entries() == []

    harness.queue_permission_cancelled()
    assert isinstance(harness.client.permission_responses[0].outcome, DeniedOutcome)
    assert initialize_response.protocol_version == PROTOCOL_VERSION

    session = await harness.new_session(cwd=str(tmp_path))
    mode_response = await harness.set_mode("review")
    model_response = await harness.set_model("provider-model-b")
    prompt_response = await harness.prompt_text("hello")

    assert session.session_id == harness.last_session_id
    assert mode_response is not None
    assert model_response is not None
    assert prompt_response.stop_reason == "end_turn"
    assert harness.updates()
    assert harness.tool_updates() == []
    assert harness.agent_messages() == ["provider:model-b"]


async def test_black_box_harness_exposes_compatibility_surface_updates(tmp_path: Path) -> None:
    harness = BlackBoxHarness.create(
        agent=Agent(TestModel(custom_output_text="surface")),
        config=AdapterConfig(
            config_options_provider=DemoConfigOptionsProvider(),
            modes_provider=DemoModesProvider(),
            plan_provider=DemoPlanProvider(),
        ),
    )

    session = await harness.new_session(cwd=str(tmp_path))
    config_response = await harness.set_config_option("stream_enabled", True)
    mode_response = await harness.set_mode("review")

    assert config_response is not None
    assert mode_response is not None
    assert harness.session_info_updates(session_id=session.session_id)
    assert harness.config_option_updates(session_id=session.session_id)
    assert harness.current_mode_id(session_id=session.session_id) == "review"
    assert [
        entry.content for entry in harness.last_plan_entries(session_id=session.session_id)
    ] == [
        "mode:review",
        "stream:true",
    ]
    assert harness.thought_chunks(session_id=session.session_id) == []
    assert harness.usage_updates(session_id=session.session_id) == []


async def test_black_box_harness_exposes_available_commands_and_permission_requests(
    tmp_path: Path,
) -> None:
    agent = Agent(TestModel(call_tools=["dangerous"]), deps_type=type(None))

    @agent.tool
    def dangerous(ctx: RunContext[None], path: str) -> str:
        if not ctx.tool_call_approved:
            raise ApprovalRequired()
        return f"approved:{path}"  # pragma: no cover

    harness = BlackBoxHarness.create(
        agent=agent,
        config=AdapterConfig(session_store=FileSessionStore(tmp_path / "sessions")),
    )
    session = await harness.new_session(cwd=str(tmp_path))
    harness.queue_permission_cancelled()

    response = await harness.prompt_text("Use the dangerous tool.")

    assert response.stop_reason == "cancelled"
    assert "tools" in harness.available_command_names(session_id=session.session_id)
    harness.clear_updates()
    assert harness.available_command_names(session_id=session.session_id) == []
    assert harness.permission_requests()
    assert harness.permission_requests(session_id=session.session_id)
    assert harness.permission_request_option_ids()
    assert harness.permission_request_option_ids(session_id=session.session_id)
    assert harness.permission_request_option_names()
    assert harness.permission_request_option_names(session_id=session.session_id)
    assert harness.last_permission_request(session_id=session.session_id) is not None


async def test_black_box_harness_load_session_returns_none_for_missing_state(
    tmp_path: Path,
) -> None:
    harness = BlackBoxHarness.create(agent=Agent(TestModel(custom_output_text="missing-session")))
    harness.last_session_id = "missing"

    response = await harness.load_session(cwd=str(tmp_path))

    assert response is None
    assert harness.last_session_id == "missing"


async def test_black_box_harness_wraps_session_lifecycle_methods(tmp_path: Path) -> None:
    harness = BlackBoxHarness.create(
        agent=Agent(TestModel(custom_output_text="lifecycle")),
        config=AdapterConfig(session_store=FileSessionStore(tmp_path / "sessions")),
    )

    session = await harness.new_session(cwd=str(tmp_path))
    listed = await harness.list_sessions(cwd=str(tmp_path))
    forked = await harness.fork_session(cwd=str(tmp_path), session_id=session.session_id)
    assert forked.session_id == harness.last_session_id

    resumed = await harness.resume_session(cwd=str(tmp_path), session_id=session.session_id)
    closed = await harness.close_session(session_id=forked.session_id)

    assert any(item.session_id == session.session_id for item in listed.sessions)
    assert resumed is not None
    assert harness.last_session_id == session.session_id
    assert closed is not None
