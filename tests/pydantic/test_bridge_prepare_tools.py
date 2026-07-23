from __future__ import annotations as _annotations

import asyncio
from collections.abc import Awaitable
from typing import Any, cast

import pytest
from pydantic_ai.capabilities import PrepareOutputTools

from .support import (
    UTC,
    AcpSessionContext,
    Agent,
    Path,
    PrepareOutputToolsBridge,
    PrepareOutputToolsMode,
    PrepareToolsBridge,
    PrepareToolsMode,
    RunContext,
    SessionConfigOptionSelect,
    TestModel,
    ToolDefinition,
    datetime,
)


def _passthrough_tools(
    ctx: RunContext[None],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    del ctx
    return list(tool_defs)


def test_passthrough_tools_helper_returns_a_copy() -> None:
    tool_defs: list[ToolDefinition] = []
    copied = _passthrough_tools(cast("Any", None), tool_defs)
    assert copied == []
    assert copied is not tool_defs


def test_prepare_output_tools_bridge_builds_capability_and_metadata(
    tmp_path: Path,
) -> None:
    def keep_public(
        ctx: RunContext[None],
        tool_defs: list[ToolDefinition],
    ) -> list[ToolDefinition]:
        del ctx
        return [tool_def for tool_def in tool_defs if tool_def.name == "public"]

    bridge = PrepareOutputToolsBridge(
        default_mode_id="default",
        modes=[
            PrepareOutputToolsMode(
                id="default",
                name="Default",
                description="Default output tools.",
                prepare_func=keep_public,
            ),
            PrepareOutputToolsMode(
                id="strict",
                name="Strict",
                description=None,
                prepare_func=_passthrough_tools,
            ),
        ],
    )
    session = AcpSessionContext(
        session_id="prepare-output-tools",
        cwd=tmp_path,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    tool_defs = [ToolDefinition(name="public"), ToolDefinition(name="private")]

    async def run_prepare() -> list[ToolDefinition]:
        prepared = bridge.build_prepare_output_tools(session)
        result = cast("Awaitable[list[ToolDefinition]]", prepared(cast("Any", None), tool_defs))
        return await result

    capability = bridge.build_capability(session)
    contributions = bridge.build_agent_capabilities(session)
    prepared_tools = asyncio.run(run_prepare())
    metadata = bridge.get_session_metadata(session, Agent(TestModel()))

    assert isinstance(capability, PrepareOutputTools)
    assert len(contributions) == 1
    assert isinstance(contributions[0], PrepareOutputTools)
    assert [tool_def.name for tool_def in prepared_tools] == ["public"]
    assert metadata == {
        "current_mode_id": "default",
        "modes": [
            {
                "description": "Default output tools.",
                "id": "default",
                "name": "Default",
            },
            {
                "description": None,
                "id": "strict",
                "name": "Strict",
            },
        ],
    }

    mode_state = bridge.set_mode(session, Agent(TestModel()), "strict")
    assert mode_state is not None
    assert mode_state.current_mode_id == "strict"
    assert bridge.get_mode_state(session, Agent(TestModel())).current_mode_id == "strict"
    session.config_values["prepare_output_tools_mode"] = "missing"
    assert bridge.get_mode_state(session, Agent(TestModel())).current_mode_id == "default"
    assert bridge.set_mode(session, Agent(TestModel()), "missing") is None

    updates = bridge.drain_updates(session, Agent(TestModel()))
    assert updates is not None


def test_prepare_output_tools_bridge_validation_and_failure_paths(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="requires at least one mode"):
        PrepareOutputToolsBridge(default_mode_id="x", modes=[])
    with pytest.raises(ValueError, match="default mode"):
        PrepareOutputToolsBridge(
            default_mode_id="missing",
            modes=[
                PrepareOutputToolsMode(
                    id="default",
                    name="Default",
                    prepare_func=_passthrough_tools,
                ),
            ],
        )
    with pytest.raises(ValueError, match="reserved slash command names"):
        PrepareOutputToolsBridge(
            default_mode_id="model",
            modes=[
                PrepareOutputToolsMode(
                    id="model",
                    name="Model",
                    prepare_func=_passthrough_tools,
                ),
            ],
        )

    def boom(
        ctx: RunContext[None],
        tool_defs: list[ToolDefinition],
    ) -> list[ToolDefinition]:
        del ctx, tool_defs
        raise RuntimeError("output boom")

    bridge = PrepareOutputToolsBridge(
        default_mode_id="default",
        modes=[
            PrepareOutputToolsMode(
                id="default",
                name="Default",
                prepare_func=boom,
            ),
        ],
    )
    session = AcpSessionContext(
        session_id="prepare-output-tools-failure",
        cwd=tmp_path,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def run_prepare() -> None:
        prepared = bridge.build_prepare_output_tools(session)
        result = cast("Awaitable[list[ToolDefinition]]", prepared(cast("Any", None), []))
        await result

    with pytest.raises(RuntimeError, match="output boom"):
        asyncio.run(run_prepare())
    with pytest.raises(ValueError, match="Unknown prepare output tools mode"):
        bridge._require_mode("missing")

    updates = bridge.drain_updates(session, Agent(TestModel()))
    assert updates is not None


def test_prepare_tools_bridge_allows_at_most_one_plan_mode() -> None:
    with pytest.raises(ValueError, match="at most one `plan_mode=True`"):
        PrepareToolsBridge(
            default_mode_id="chat",
            modes=[
                PrepareToolsMode(
                    id="chat",
                    name="Chat",
                    prepare_func=_passthrough_tools,
                    plan_mode=True,
                ),
                PrepareToolsMode(
                    id="plan",
                    name="Plan",
                    prepare_func=_passthrough_tools,
                    plan_mode=True,
                ),
            ],
        )


def test_prepare_tools_bridge_rejects_invalid_default_plan_generation_type() -> None:
    with pytest.raises(ValueError, match="default plan generation type"):
        PrepareToolsBridge(
            default_mode_id="plan",
            modes=[
                PrepareToolsMode(
                    id="plan",
                    name="Plan",
                    prepare_func=_passthrough_tools,
                    plan_mode=True,
                ),
            ],
            default_plan_generation_type=cast("Any", "invalid"),
        )


def test_prepare_tools_bridge_can_enable_plan_tools_outside_plan_mode() -> None:
    bridge = PrepareToolsBridge(
        default_mode_id="agent",
        modes=[
            PrepareToolsMode(
                id="plan",
                name="Plan",
                prepare_func=_passthrough_tools,
                plan_mode=True,
            ),
            PrepareToolsMode(
                id="agent",
                name="Agent",
                prepare_func=_passthrough_tools,
                plan_tools=True,
            ),
        ],
    )

    session = AcpSessionContext(
        session_id="plan-tools",
        cwd=Path("/tmp"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        config_values={"mode": "agent"},
    )

    assert bridge.is_plan_mode(session) is False
    assert bridge.supports_plan_tools(session) is True
    assert bridge.supports_plan_write_tools(session) is True
    assert bridge.supports_plan_progress(session) is True
    config_options = bridge.get_config_options(session, Agent(TestModel()))
    assert len(config_options) == 1
    assert config_options[0].id == "plan_generation_type"
    assert (
        bridge.set_config_option(
            session,
            Agent(TestModel()),
            "plan_generation_type",
            "tools",
        )
        is not None
    )


def test_prepare_tools_bridge_exposes_plan_generation_config_and_helpers() -> None:
    bridge = PrepareToolsBridge(
        default_mode_id="plan",
        modes=[
            PrepareToolsMode(
                id="plan",
                name="Plan",
                prepare_func=_passthrough_tools,
                plan_mode=True,
            ),
            PrepareToolsMode(
                id="agent",
                name="Agent",
                prepare_func=_passthrough_tools,
                plan_tools=True,
            ),
        ],
    )
    session = AcpSessionContext(
        session_id="plan-generation",
        cwd=Path("/tmp"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    agent = Agent(TestModel())

    config_options = bridge.get_config_options(session, agent)
    assert len(config_options) == 1
    assert isinstance(config_options[0], SessionConfigOptionSelect)
    assert config_options[0].id == "plan_generation_type"
    assert config_options[0].current_value == "structured"
    assert bridge.uses_structured_plan_generation(session) is True
    assert bridge.supports_plan_write_tools(session) is False
    metadata = bridge.get_session_metadata(session, agent)
    assert metadata["current_plan_generation_type"] == "structured"
    assert metadata["supported_plan_generation_types"] == ["tools", "structured"]

    updated = bridge.set_config_option(session, agent, "plan_generation_type", "tools")
    assert updated is not None
    assert bridge.current_plan_generation_type(session) == "tools"
    assert bridge.uses_tool_plan_generation(session) is True
    assert bridge.supports_plan_write_tools(session) is True
    reset = bridge.set_config_option(session, agent, "plan_generation_type", "structured")
    assert reset is not None
    assert bridge.current_plan_generation_type(session) == "structured"
    assert "plan_generation_type" not in session.config_values

    session.config_values["mode"] = "agent"
    assert bridge.supports_plan_progress(session) is True
    assert bridge.supports_plan_write_tools(session) is True
    assert bridge.set_config_option(session, agent, "plan_generation_type", True) is None
    assert bridge.set_config_option(session, agent, "plan_generation_type", "invalid") is None
    session.config_values["plan_generation_type"] = "invalid"
    assert bridge.current_plan_generation_type(session) == "structured"


def test_prepare_tools_bridge_records_failure_events(tmp_path: Path) -> None:
    def boom(
        ctx: RunContext[None],
        tool_defs: list[ToolDefinition],
    ) -> list[ToolDefinition]:
        del ctx, tool_defs
        raise RuntimeError("boom")

    bridge = PrepareToolsBridge(
        default_mode_id="plan",
        modes=[
            PrepareToolsMode(
                id="plan",
                name="Plan",
                prepare_func=boom,
                plan_mode=True,
            ),
        ],
    )
    session = AcpSessionContext(
        session_id="prepare-tools-failure",
        cwd=tmp_path,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def run_prepare() -> None:
        prepared = bridge.build_prepare_tools(session)
        result = prepared(cast("Any", None), [])
        if asyncio.iscoroutine(result):
            await result
            return  # pragma: no cover
        assert result == []  # pragma: no cover

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(run_prepare())

    updates = bridge.drain_updates(session, Agent(TestModel()))
    assert updates is not None


def test_prepare_tools_bridge_rejects_reserved_mode_ids() -> None:
    with pytest.raises(ValueError, match="reserved slash command names"):
        PrepareToolsBridge(
            default_mode_id="model",
            modes=[
                PrepareToolsMode(
                    id="model",
                    name="Model",
                    prepare_func=_passthrough_tools,
                ),
            ],
        )
