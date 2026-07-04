from __future__ import annotations as _annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
from acp import PROTOCOL_VERSION
from acp.helpers import text_block
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    ClientCapabilities,
    Implementation,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    Usage,
)
from pydantic_ai import Agent
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelRequest, SystemPromptPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers import Provider

from pydantic_acp import (
    AcpHostBridge,
    AcpModel,
    AcpProvider,
    BlackBoxHarness,
    RecordingACPClient,
)


class EchoACPAgent:
    def __init__(self, *, usage: Usage | None = None) -> None:
        self.client: Any | None = None
        self.initialized_protocols: list[int] = []
        self.session_cwds: list[str] = []
        self.session_models: list[tuple[str, str]] = []
        self.prompts: list[tuple[str, str]] = []
        self._usage = usage

    def on_connect(self, conn: Any) -> None:
        self.client = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        del client_capabilities, client_info, kwargs
        self.initialized_protocols.append(protocol_version)
        return InitializeResponse(
            protocol_version=protocol_version,
            agent_info=Implementation(name="echo-acp-agent", version="test"),
            agent_capabilities=AgentCapabilities(),
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        del mcp_servers, kwargs
        self.session_cwds.append(cwd)
        return NewSessionResponse(session_id=f"session-{len(self.session_cwds)}")

    async def set_session_model(
        self,
        model_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        del kwargs
        self.session_models.append((session_id, model_id))

    async def prompt(
        self,
        prompt: list[Any],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> PromptResponse:
        del message_id, kwargs
        if self.client is None:
            raise AssertionError("ACP agent was not connected to a host client")
        rendered_prompt = "".join(str(getattr(block, "text", "")) for block in prompt)
        self.prompts.append((session_id, rendered_prompt))
        await self.client.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                session_update="agent_message_chunk",
                content=text_block(f"acp echo: {rendered_prompt}"),
            ),
            source="echo-acp-agent",
        )
        return PromptResponse(stop_reason="end_turn", usage=self._usage)


class HostRequestingACPAgent(EchoACPAgent):
    """ACP agent whose turn requires delegating a filesystem write to the host."""

    async def prompt(
        self,
        prompt: list[Any],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> PromptResponse:
        del message_id, kwargs
        rendered_prompt = "".join(str(getattr(block, "text", "")) for block in prompt)
        self.prompts.append((session_id, rendered_prompt))
        await self.client.write_text_file(
            content=rendered_prompt,
            path="/workspace/notes.txt",
            session_id=session_id,
        )
        await self.client.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                session_update="agent_message_chunk",
                content=text_block("saved"),
            ),
        )
        return PromptResponse(stop_reason="end_turn")


def test_acp_client_provider_is_plain_pydantic_ai_provider() -> None:
    acp_agent = EchoACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)

    assert isinstance(provider, Provider)
    assert provider.client is acp_agent
    assert provider.name == "acp"
    assert provider.base_url == "acp://local"
    assert model.provider is provider
    assert model.system == "acp"
    assert model.model_name == "zed-agent"
    assert model.base_url == "acp://local"


async def test_pydantic_ai_agent_can_use_acp_as_just_a_provider() -> None:
    acp_agent = EchoACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)
    agent = Agent(model)

    result = await agent.run("Summarize the ACP bridge")

    assert "Summarize the ACP bridge" in result.output
    assert acp_agent.initialized_protocols == [PROTOCOL_VERSION]
    assert acp_agent.session_cwds == ["/workspace"]
    assert acp_agent.session_models == [("session-1", "zed-agent")]
    assert len(acp_agent.prompts) == 1
    assert "Summarize the ACP bridge" in acp_agent.prompts[0][1]


def test_pydantic_acp_requires_pydantic_ai_v2() -> None:
    package_pyproject = Path("packages/adapters/pydantic-acp/pyproject.toml")
    data = tomllib.loads(package_pyproject.read_text())
    dependencies = data["project"]["dependencies"]
    pydantic_ai_dependency = next(
        dependency for dependency in dependencies if dependency.startswith("pydantic-ai-slim")
    )

    assert ">=2.0.0" in pydantic_ai_dependency
    assert "==1." not in pydantic_ai_dependency


async def test_acp_provider_reuses_session_across_multiple_runs() -> None:
    """Changed-code coverage: a provider/model pair is reused across independent
    agent runs, so ACP session setup (initialize/new_session/set_session_model)
    only happens once even though the ACP agent handles two separate prompts.
    """
    acp_agent = EchoACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)
    agent = Agent(model)

    await agent.run("first turn")
    await agent.run("second turn")

    assert acp_agent.initialized_protocols == [PROTOCOL_VERSION]
    assert acp_agent.session_cwds == ["/workspace"]
    assert acp_agent.session_models == [("session-1", "zed-agent")]
    assert [session_id for session_id, _ in acp_agent.prompts] == ["session-1", "session-1"]


async def test_acp_model_carries_through_prompt_response_usage() -> None:
    """Changed-code coverage: ACP-reported token usage on the prompt response is
    translated into the Pydantic AI ``RequestUsage`` carried by the run result.
    """
    usage = Usage(input_tokens=11, output_tokens=7, total_tokens=18)
    acp_agent = EchoACPAgent(usage=usage)
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)
    agent = Agent(model)

    result = await agent.run("Count my tokens")

    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7


async def test_acp_model_supports_streaming() -> None:
    """Changed-code coverage: ``AcpModel.request_stream`` lets a regular Pydantic
    AI agent stream text even though ACP delivers the turn as a single prompt.
    """
    acp_agent = EchoACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)
    agent = Agent(model)

    async with agent.run_stream("Stream this") as stream_result:
        streamed_text = await stream_result.get_output()

    assert "Stream this" in streamed_text
    assert acp_agent.prompts == [("session-1", "Stream this")]


async def test_acp_model_rejects_function_tools() -> None:
    """Changed-code coverage: ``AcpModel`` cannot execute Pydantic AI function
    tools itself, so registering one on the agent must fail clearly instead of
    being silently ignored.
    """
    acp_agent = EchoACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)
    agent = Agent(model)

    @agent.tool_plain
    def get_time() -> str:
        return "12:00"

    with pytest.raises(UserError, match="function tools"):
        await agent.run("What time is it?")


async def test_default_prompt_renderer_includes_system_and_tool_return_sections() -> None:
    """Changed-code coverage: the default prompt renderer used by ``AcpProvider``
    folds system prompts, tool results, and user text into the single ACP text
    block sent to the wrapped ACP agent.
    """
    acp_agent = EchoACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart(content="Be helpful."),
                ToolReturnPart(tool_name="lookup", tool_call_id="1", content="42"),
                UserPromptPart(content="Hello there"),
            ]
        )
    ]

    blocks = await provider.render_prompt_blocks(messages, ModelRequestParameters())

    assert len(blocks) == 1
    rendered_text = blocks[0].text
    assert "Be helpful." in rendered_text
    assert "lookup" in rendered_text
    assert "42" in rendered_text
    assert "Hello there" in rendered_text


async def test_acp_host_bridge_forwards_host_requests_to_delegate() -> None:
    """Changed-code coverage: when a host client delegate is supplied, ACP host
    operations requested by the wrapped agent (e.g. writing a file) are
    forwarded to that real host client instead of failing.
    """
    delegate = RecordingACPClient()
    acp_agent = HostRequestingACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace", host_client=delegate)
    model = AcpModel(model_name="zed-agent", provider=provider)
    agent = Agent(model)

    result = await agent.run("Persist this note")

    assert result.output == "saved"
    assert delegate.write_calls == [("session-1", "/workspace/notes.txt", "Persist this note")]


async def test_acp_host_bridge_raises_clearly_without_delegate() -> None:
    """Prior/default-path coverage: this is the baseline ``AcpProvider`` behavior
    (no ``host_client`` supplied). Host operations must fail explicitly rather
    than being silently swallowed, exactly as before the delegate-forwarding
    feature was layered on top.
    """
    acp_agent = HostRequestingACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)
    agent = Agent(model)

    with pytest.raises(RuntimeError, match="write_text_file"):
        await agent.run("Persist this note")


async def test_acp_host_bridge_low_level_delegate_forwarding() -> None:
    """Changed-code coverage: unit-level check that ``AcpHostBridge`` forwards a
    host method call to its delegate and returns the delegate's response.
    """
    delegate = RecordingACPClient()
    bridge = AcpHostBridge(delegate=delegate)

    response = await bridge.write_text_file(content="hello", path="/tmp/note.txt", session_id="session-1")

    assert delegate.write_calls == [("session-1", "/tmp/note.txt", "hello")]
    assert response is delegate.write_response


async def test_acp_host_bridge_low_level_raises_without_delegate() -> None:
    """Prior/default-path coverage: the bare ``AcpHostBridge`` (no delegate at
    all) is the original, minimal behavior this class was built around.
    """
    bridge = AcpHostBridge()

    with pytest.raises(RuntimeError, match="write_text_file"):
        await bridge.write_text_file(content="hello", path="/tmp/note.txt", session_id="session-1")


def test_acp_host_bridge_forwards_on_connect_to_delegate() -> None:
    """Changed-code coverage: reverse ACP connections are forwarded to a host
    client delegate when it supports ``on_connect``.
    """

    class ConnectRecordingDelegate(RecordingACPClient):
        connected_agent: Any = None

        def on_connect(self, conn: Any) -> None:
            self.connected_agent = conn

    delegate = ConnectRecordingDelegate()
    bridge = AcpHostBridge(delegate=delegate)
    sentinel = object()

    bridge.on_connect(sentinel)

    assert delegate.connected_agent is sentinel


async def test_server_side_acp_bridge_unaffected_by_client_bridge_addition() -> None:
    """Prior-behavior-path regression coverage: this PR adds the inverse
    client-provider bridge in ``client.py``. The pre-existing server-side
    direction (exposing a ``pydantic_ai.Agent`` through ACP via
    ``create_acp_agent``) must keep working unchanged.
    """
    harness = BlackBoxHarness.create(agent=Agent(TestModel(custom_output_text="server-side-ok")))

    await harness.initialize()
    session = await harness.new_session(cwd="/workspace")
    prompt_response = await harness.prompt_text("ping", session_id=session.session_id)

    assert prompt_response.stop_reason == "end_turn"
    assert harness.agent_messages(session_id=session.session_id) == ["server-side-ok"]
