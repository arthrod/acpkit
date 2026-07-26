from __future__ import annotations as _annotations

import asyncio
from typing import Any

from acp import PROTOCOL_VERSION
from acp.helpers import text_block
from pydantic_acp import CapabilityBridge, RuntimeAgent
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.settings import ModelSettings

from .support import (
    AcpSessionContext,
    AdapterConfig,
    MemorySessionStore,
    RecordingClient,
    create_acp_agent,
)


def _capture_model(captured: list[ModelSettings | None]) -> FunctionModel:
    def call(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        captured.append(info.model_settings)
        return ModelResponse(parts=[TextPart("ok")])

    return FunctionModel(call)


class _SettingsBridge(CapabilityBridge):
    def get_model_settings(
        self,
        session: AcpSessionContext,
        agent: RuntimeAgent,
    ) -> ModelSettings | None:
        del session, agent
        return ModelSettings(timeout=0.5)


async def _run_prompt(adapter: Any) -> None:
    client = RecordingClient()
    adapter.on_connect(client)
    await adapter.initialize(protocol_version=PROTOCOL_VERSION)
    session = await adapter.new_session(cwd="/workspace", mcp_servers=[])
    await adapter.prompt(
        prompt=[text_block("hello")],
        session_id=session.session_id,
        message_id="user-message-1",
    )


def test_adapter_config_model_settings_reach_model_requests() -> None:
    captured: list[ModelSettings | None] = []
    adapter = create_acp_agent(
        agent=Agent(_capture_model(captured)),
        config=AdapterConfig(
            model_settings=ModelSettings(timeout=12.5, temperature=0.25),
            session_store=MemorySessionStore(),
        ),
    )

    asyncio.run(_run_prompt(adapter))

    assert captured
    for settings in captured:
        assert settings is not None
        assert settings.get("timeout") == 12.5
        assert settings.get("temperature") == 0.25


def test_bridge_model_settings_override_config_defaults_per_key() -> None:
    captured: list[ModelSettings | None] = []
    adapter = create_acp_agent(
        agent=Agent(_capture_model(captured)),
        config=AdapterConfig(
            model_settings=ModelSettings(timeout=12.5, temperature=0.25),
            capability_bridges=[_SettingsBridge()],
            session_store=MemorySessionStore(),
        ),
    )

    asyncio.run(_run_prompt(adapter))

    assert captured
    for settings in captured:
        assert settings is not None
        assert settings.get("timeout") == 0.5
        assert settings.get("temperature") == 0.25


def test_adapter_without_config_model_settings_passes_none() -> None:
    captured: list[ModelSettings | None] = []
    adapter = create_acp_agent(
        agent=Agent(_capture_model(captured)),
        config=AdapterConfig(session_store=MemorySessionStore()),
    )

    asyncio.run(_run_prompt(adapter))

    assert captured
    assert all(settings is None for settings in captured)
