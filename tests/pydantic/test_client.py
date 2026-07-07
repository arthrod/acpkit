from __future__ import annotations as _annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from acp import PROTOCOL_VERSION
from acp.helpers import text_block
from acp.schema import (
    AgentMessageChunk,
    ClientCapabilities,
    HttpMcpServer,
    Implementation,
    TextContentBlock,
)
from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import RetryPromptPart, SystemPromptPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition
from pydantic_acp import AdapterConfig, MemorySessionStore, create_acp_agent
from pydantic_acp.client import (
    ACPModel,
    ACPProvider,
    _extract_response_text,
    _extract_update_text,
    _latest_model_request,
    _render_prompt_text,
    _response_field,
    _stringify_content,
)

# ---------------------------------------------------------------------------
# Test doubles standing in for the ACP transport boundary.
#
# `ACPClientConnection` (used by `FakeACPClient`) and `acp.interfaces.Agent`
# (used by `FakeACPAgent`) are the transport-layer seams in this module.
# Tests mock at those seams instead of patching methods on `ACPProvider` or
# `ACPModel` directly.
# ---------------------------------------------------------------------------


class FakeACPClient:
    """Stand-in for the ACP client-side connection (`ACPClientConnection`)."""

    def __init__(
        self,
        *,
        session_id: str = "session-1",
        new_session_response: Any = None,
        prompt_response: Any = None,
        streamed_updates: list[tuple[str, Any]] | None = None,
    ) -> None:
        self.initialize_calls: list[dict[str, Any]] = []
        self.new_session_calls: list[dict[str, Any]] = []
        self.prompt_calls: list[dict[str, Any]] = []
        self.cancel_calls: list[str] = []
        self.close_session_calls: list[str] = []
        self._session_id = session_id
        self._new_session_response = (
            new_session_response
            if new_session_response is not None
            else {"session_id": session_id}
        )
        self._prompt_response = prompt_response
        self.streamed_updates = list(streamed_updates or [])
        self.provider: ACPProvider | None = None

    async def initialize(
        self,
        *,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> Any:
        self.initialize_calls.append(
            {
                "protocol_version": protocol_version,
                "client_capabilities": client_capabilities,
                "client_info": client_info,
                **kwargs,
            }
        )
        return {}

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self.new_session_calls.append({"cwd": cwd, "mcp_servers": mcp_servers, **kwargs})
        return self._new_session_response

    async def prompt(
        self,
        *,
        prompt: list[Any],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        self.prompt_calls.append(
            {"prompt": prompt, "session_id": session_id, "message_id": message_id, **kwargs}
        )
        if self.provider is not None:
            for update_session_id, update in self.streamed_updates:
                await self.provider.session_update(update_session_id, update)
        return self._prompt_response

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        del kwargs
        self.cancel_calls.append(session_id)

    async def close_session(self, session_id: str, **kwargs: Any) -> Any:
        del kwargs
        self.close_session_calls.append(session_id)
        return None


class FakeACPAgent:
    """Minimal stand-in for `acp.interfaces.Agent` used to exercise `from_agent`."""

    def __init__(self, *, session_id: str = "agent-session", prompt_response: Any = None) -> None:
        self.connected_client: Any = None
        self.initialize_calls: list[int] = []
        self.new_session_calls: list[str] = []
        self.prompt_calls: list[tuple[list[Any], str, str | None]] = []
        self._session_id = session_id
        self._prompt_response = prompt_response

    def on_connect(self, conn: Any) -> None:
        self.connected_client = conn

    async def initialize(
        self,
        *,
        protocol_version: int,
        client_capabilities: Any = None,
        client_info: Any = None,
        **kwargs: Any,
    ) -> Any:
        del client_capabilities, client_info, kwargs
        self.initialize_calls.append(protocol_version)
        return {}

    async def new_session(self, cwd: str, mcp_servers: list[Any] | None = None, **kwargs: Any) -> Any:
        del mcp_servers, kwargs
        self.new_session_calls.append(cwd)
        return {"session_id": self._session_id}

    async def prompt(
        self,
        *,
        prompt: list[Any],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        del kwargs
        self.prompt_calls.append((prompt, session_id, message_id))
        return self._prompt_response


class _BinaryBlob:
    def __init__(self) -> None:
        self.data = b"raw-bytes"


class _ImagePlaceholder:
    pass


# ---------------------------------------------------------------------------
# Pure helper functions.
# ---------------------------------------------------------------------------


def test_response_field_reads_dict_object_and_missing_values() -> None:
    class Obj:
        session_id = "from-object"

    assert _response_field({"session_id": "abc"}, "session_id", "sessionId") == "abc"
    assert _response_field({"sessionId": "camel"}, "session_id", "sessionId") == "camel"
    assert _response_field(Obj(), "session_id", "sessionId") == "from-object"
    assert _response_field({}, "session_id", "sessionId") is None
    assert _response_field(None, "session_id", "sessionId") is None


def test_extract_response_text_concatenates_matching_fields_in_priority_order() -> None:
    response = {
        "text": "part-a",
        "output_text": "part-b",
        "content": "part-c",
        "message": "part-d",
        "unrelated": "ignored",
    }

    assert _extract_response_text(response) == "part-apart-bpart-cpart-d"


def test_extract_response_text_returns_empty_string_for_none_or_non_string_fields() -> None:
    class Obj:
        text = None
        message = 123

    assert _extract_response_text(None) == ""
    assert _extract_response_text(Obj()) == ""


def test_extract_update_text_from_plain_text_content_block() -> None:
    block = TextContentBlock(type="text", text="hello world")

    assert _extract_update_text(block) == "hello world"


def test_extract_update_text_from_agent_message_chunk_wrapping_text_block() -> None:
    chunk = AgentMessageChunk(
        session_update="agent_message_chunk",
        message_id="m1",
        content=text_block("nested text"),
    )

    assert _extract_update_text(chunk) == "nested text"


def test_extract_update_text_returns_empty_string_for_unrelated_or_missing_updates() -> None:
    class UnrelatedUpdate:
        pass

    assert _extract_update_text(UnrelatedUpdate()) == ""
    assert _extract_update_text(None) == ""


def test_stringify_content_handles_plain_string() -> None:
    assert _stringify_content("hello") == "hello"


def test_stringify_content_joins_sequence_of_parts() -> None:
    assert _stringify_content(["a", "b"]) == "a\nb"


def test_stringify_content_returns_placeholder_for_content_with_data_attribute() -> None:
    assert _stringify_content(_BinaryBlob()) == "[_BinaryBlob]"


def test_stringify_content_returns_placeholder_for_image_like_type_name() -> None:
    assert _stringify_content(_ImagePlaceholder()) == "[_ImagePlaceholder]"


def test_stringify_content_returns_empty_string_for_none() -> None:
    assert _stringify_content(None) == ""


def test_stringify_content_falls_back_to_str_for_other_values() -> None:
    assert _stringify_content(42) == "42"


def test_latest_model_request_returns_last_request_type() -> None:
    request_one = ModelRequest(parts=[UserPromptPart(content="one")])
    response = ModelResponse(parts=[TextPart(content="ack")])
    request_two = ModelRequest(parts=[UserPromptPart(content="two")])

    assert _latest_model_request([request_one, response, request_two]) is request_two


def test_latest_model_request_falls_back_to_last_message_when_no_request_present() -> None:
    response = ModelResponse(parts=[TextPart(content="only assistant turn")])

    assert _latest_model_request([response]) is response


def test_latest_model_request_returns_none_for_empty_list() -> None:
    assert _latest_model_request([]) is None


def test_render_prompt_text_latest_user_mode_sends_only_the_last_user_turn() -> None:
    messages = [
        ModelRequest(parts=[UserPromptPart(content="first turn")]),
        ModelResponse(parts=[TextPart(content="assistant reply")]),
        ModelRequest(parts=[UserPromptPart(content="second turn")]),
    ]

    rendered = _render_prompt_text(messages, history_mode="latest_user")

    assert rendered == "second turn"


def test_render_prompt_text_full_mode_serializes_the_entire_conversation() -> None:
    messages = [
        ModelRequest(parts=[UserPromptPart(content="first turn")]),
        ModelResponse(parts=[TextPart(content="assistant reply")]),
    ]

    rendered = _render_prompt_text(messages, history_mode="full")

    assert "<user>" in rendered and "first turn" in rendered
    assert "<assistant>" in rendered and "assistant reply" in rendered


def test_render_prompt_text_falls_back_to_full_history_when_latest_request_is_blank() -> None:
    request_one = ModelRequest(parts=[UserPromptPart(content="original question")])
    response = ModelResponse(parts=[TextPart(content="original answer")])
    blank_request = ModelRequest(parts=[UserPromptPart(content="   ")])

    rendered = _render_prompt_text(
        [request_one, response, blank_request], history_mode="latest_user"
    )

    assert "<user>" in rendered and "original question" in rendered
    assert "<assistant>" in rendered and "original answer" in rendered


def test_render_prompt_text_renders_system_tool_call_and_tool_return_parts() -> None:
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart(content="be helpful"),
                UserPromptPart(content="run the tool"),
            ]
        ),
        ModelResponse(parts=[ToolCallPart("echo", {"text": "hi"})]),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name="echo", content="done", tool_call_id="tc-1"),
                RetryPromptPart("try again", tool_name="echo", tool_call_id="tc-2"),
            ]
        ),
    ]

    rendered = _render_prompt_text(messages, history_mode="full")

    assert "<system>be helpful</system>" in rendered
    assert "[tool-call:echo] {'text': 'hi'}" in rendered
    assert "[tool-result:tc-1] done" in rendered
    assert "[tool-result:tc-2] try again" in rendered


# ---------------------------------------------------------------------------
# ACPProvider: session lifecycle.
# ---------------------------------------------------------------------------


def test_provider_without_a_configured_client_raises_on_ensure_session() -> None:
    provider = ACPProvider()

    with pytest.raises(RuntimeError, match="no ACP client connection configured"):
        asyncio.run(provider.ensure_session())


def test_ensure_session_initializes_client_and_creates_session() -> None:
    client = FakeACPClient(session_id="session-abc")
    provider = ACPProvider(client=client, cwd="/tmp/workspace")

    session_id = asyncio.run(provider.ensure_session())

    assert session_id == "session-abc"
    assert provider.session_id == "session-abc"
    assert len(client.initialize_calls) == 1
    assert client.initialize_calls[0]["protocol_version"] == PROTOCOL_VERSION
    assert isinstance(client.initialize_calls[0]["client_capabilities"], ClientCapabilities)
    assert client.initialize_calls[0]["client_info"] == Implementation(
        name="pydantic-acp", version="2"
    )
    assert len(client.new_session_calls) == 1
    assert client.new_session_calls[0]["cwd"] == "/tmp/workspace"


def test_ensure_session_forwards_custom_capabilities_and_protocol_version() -> None:
    client = FakeACPClient()
    custom_caps = ClientCapabilities()
    custom_info = Implementation(name="custom-host", version="9")
    provider = ACPProvider(
        client=client,
        client_capabilities=custom_caps,
        client_info=custom_info,
        protocol_version=7,
    )

    asyncio.run(provider.ensure_session())

    call = client.initialize_calls[0]
    assert call["protocol_version"] == 7
    assert call["client_capabilities"] is custom_caps
    assert call["client_info"] is custom_info


def test_ensure_session_forwards_mcp_servers_to_new_session() -> None:
    client = FakeACPClient()
    servers = [HttpMcpServer(name="docs", url="https://example.invalid/mcp", headers=[], type="http")]
    provider = ACPProvider(client=client, mcp_servers=servers)

    asyncio.run(provider.ensure_session())

    assert client.new_session_calls[0]["mcp_servers"] == servers


def test_ensure_session_accepts_camel_case_session_id_field() -> None:
    client = FakeACPClient(new_session_response={"sessionId": "camel-session"})
    provider = ACPProvider(client=client)

    session_id = asyncio.run(provider.ensure_session())

    assert session_id == "camel-session"


def test_ensure_session_raises_when_response_missing_session_id() -> None:
    client = FakeACPClient(new_session_response={})
    provider = ACPProvider(client=client)

    with pytest.raises(RuntimeError, match="did not include a session id"):
        asyncio.run(provider.ensure_session())


def test_ensure_session_with_preset_session_id_skips_new_session_call() -> None:
    client = FakeACPClient()
    provider = ACPProvider(client=client, session_id="preset-session")

    session_id = asyncio.run(provider.ensure_session())

    assert session_id == "preset-session"
    assert len(client.initialize_calls) == 1
    assert client.new_session_calls == []


def test_ensure_session_reuses_existing_session_on_repeated_calls() -> None:
    client = FakeACPClient()
    provider = ACPProvider(client=client)

    first = asyncio.run(provider.ensure_session())
    second = asyncio.run(provider.ensure_session())

    assert first == second
    assert len(client.initialize_calls) == 1
    assert len(client.new_session_calls) == 1


def test_close_closes_session_and_clears_session_id() -> None:
    client = FakeACPClient()
    provider = ACPProvider(client=client)
    asyncio.run(provider.ensure_session())

    asyncio.run(provider.close())

    assert provider.session_id is None
    assert client.close_session_calls == ["session-1"]


def test_close_without_an_active_session_is_a_noop() -> None:
    client = FakeACPClient()
    provider = ACPProvider(client=client)

    asyncio.run(provider.close())

    assert client.close_session_calls == []


def test_provider_as_async_context_manager_ensures_and_closes_session() -> None:
    client = FakeACPClient()

    async def run() -> str | None:
        async with ACPProvider(client=client) as provider:
            return provider.session_id

    session_id = asyncio.run(run())

    assert session_id == "session-1"
    assert client.close_session_calls == ["session-1"]


def test_model_profile_always_returns_none() -> None:
    assert ACPProvider.model_profile("any-model") is None


# ---------------------------------------------------------------------------
# ACPProvider: prompting and streaming.
# ---------------------------------------------------------------------------


def test_prompt_text_returns_streamed_text_when_available() -> None:
    client = FakeACPClient(prompt_response={"text": "final-response-text"})
    provider = ACPProvider(client=client)
    client.provider = provider
    client.streamed_updates = [
        ("session-1", TextContentBlock(type="text", text="Hello ")),
        ("session-1", TextContentBlock(type="text", text="world")),
    ]

    result = asyncio.run(provider.prompt_text([TextContentBlock(type="text", text="hi")]))

    assert result == "Hello world"
    assert len(provider.updates) == 2


def test_prompt_text_falls_back_to_response_text_when_nothing_streamed() -> None:
    client = FakeACPClient(prompt_response={"text": "response-text"})
    provider = ACPProvider(client=client)

    result = asyncio.run(provider.prompt_text([TextContentBlock(type="text", text="hi")]))

    assert result == "response-text"


def test_prompt_text_returns_empty_string_when_no_text_is_available() -> None:
    client = FakeACPClient(prompt_response={})
    provider = ACPProvider(client=client)

    result = asyncio.run(provider.prompt_text([TextContentBlock(type="text", text="hi")]))

    assert result == ""


def test_prompt_text_clears_streamed_text_between_calls() -> None:
    client = FakeACPClient()
    provider = ACPProvider(client=client)
    client.provider = provider

    client.streamed_updates = [("session-1", TextContentBlock(type="text", text="first"))]
    first = asyncio.run(provider.prompt_text([TextContentBlock(type="text", text="one")]))

    client.streamed_updates = []
    client._prompt_response = {"text": "second-response"}
    second = asyncio.run(provider.prompt_text([TextContentBlock(type="text", text="two")]))

    assert first == "first"
    assert second == "second-response"


def test_prompt_text_forwards_prompt_blocks_session_id_and_message_id() -> None:
    client = FakeACPClient()
    provider = ACPProvider(client=client)

    asyncio.run(
        provider.prompt_text([TextContentBlock(type="text", text="hi")], message_id="msg-1")
    )

    assert len(client.prompt_calls) == 1
    call = client.prompt_calls[0]
    assert call["session_id"] == "session-1"
    assert call["message_id"] == "msg-1"
    assert call["prompt"] == [TextContentBlock(type="text", text="hi")]


def test_cancel_forwards_to_client_when_session_exists() -> None:
    client = FakeACPClient()
    provider = ACPProvider(client=client)
    asyncio.run(provider.ensure_session())

    asyncio.run(provider.cancel())

    assert client.cancel_calls == ["session-1"]


def test_cancel_is_a_noop_without_an_active_session() -> None:
    client = FakeACPClient()
    provider = ACPProvider(client=client)

    asyncio.run(provider.cancel())

    assert client.cancel_calls == []


def test_session_update_records_update_and_extracts_streaming_text() -> None:
    provider = ACPProvider(client=FakeACPClient())
    chunk = AgentMessageChunk(
        session_update="agent_message_chunk",
        message_id="m1",
        content=text_block("hello"),
    )

    asyncio.run(provider.session_update("session-x", chunk, extra="meta"))

    assert provider.updates == (("session-x", chunk, {"extra": "meta"}),)


# ---------------------------------------------------------------------------
# ACPProvider: host-client callback surface (permissions and extensions).
# ---------------------------------------------------------------------------


def test_request_permission_without_a_handler_raises_permission_error() -> None:
    provider = ACPProvider(client=FakeACPClient())

    with pytest.raises(PermissionError, match="permission_handler"):
        asyncio.run(provider.request_permission([], "session-1", tool_call=object()))


def test_request_permission_awaits_async_handler_and_forwards_arguments() -> None:
    received: dict[str, Any] = {}

    async def handler(*, options: Any, session_id: str, tool_call: Any, **kwargs: Any) -> str:
        received["options"] = options
        received["session_id"] = session_id
        received["tool_call"] = tool_call
        received["extra"] = kwargs
        return "async-result"

    provider = ACPProvider(client=FakeACPClient(), permission_handler=handler)

    result = asyncio.run(
        provider.request_permission(["opt"], "session-1", tool_call="tool", extra_flag=True)
    )

    assert result == "async-result"
    assert received == {
        "options": ["opt"],
        "session_id": "session-1",
        "tool_call": "tool",
        "extra": {"extra_flag": True},
    }


def test_request_permission_supports_a_synchronous_handler() -> None:
    def handler(*, options: Any, session_id: str, tool_call: Any, **kwargs: Any) -> str:
        del options, session_id, tool_call, kwargs
        return "sync-result"

    provider = ACPProvider(client=FakeACPClient(), permission_handler=handler)

    result = asyncio.run(provider.request_permission(["opt"], "session-1", tool_call="tool"))

    assert result == "sync-result"


def test_ext_method_raises_not_implemented_with_method_name() -> None:
    provider = ACPProvider(client=FakeACPClient())

    with pytest.raises(NotImplementedError, match="ext/custom"):
        asyncio.run(provider.ext_method("ext/custom", {"a": 1}))


def test_ext_notification_is_a_noop() -> None:
    provider = ACPProvider(client=FakeACPClient())

    assert asyncio.run(provider.ext_notification("ext/custom", {"a": 1})) is None


# ---------------------------------------------------------------------------
# ACPProvider.from_agent / _DirectACPConnection.
# ---------------------------------------------------------------------------


def test_from_agent_wires_on_connect_and_forwards_lifecycle_calls() -> None:
    agent = FakeACPAgent(prompt_response={"text": "agent-response"})
    provider = ACPProvider.from_agent(agent, cwd="/workdir")

    assert agent.connected_client is provider

    result = asyncio.run(provider.prompt_text([TextContentBlock(type="text", text="hi")]))

    assert result == "agent-response"
    assert agent.new_session_calls == ["/workdir"]
    assert agent.prompt_calls[0][1] == provider.session_id


def test_from_agent_close_is_a_noop_when_the_agent_lacks_close_session() -> None:
    agent = FakeACPAgent()
    provider = ACPProvider.from_agent(agent)
    asyncio.run(provider.ensure_session())

    asyncio.run(provider.close())

    assert provider.session_id is None


# ---------------------------------------------------------------------------
# ACPModel.
# ---------------------------------------------------------------------------


def test_model_exposes_provider_derived_properties() -> None:
    provider = ACPProvider(client=FakeACPClient(), name="my-acp", base_url="acp://custom")
    model = ACPModel(provider=provider)

    assert model.model_name == "agent"
    assert model.system == "my-acp"
    assert model.base_url == "acp://custom"
    assert model.provider is provider


def test_request_sends_only_the_latest_user_turn_by_default() -> None:
    client = FakeACPClient(prompt_response={"text": "ack"})
    provider = ACPProvider(client=client)
    model = ACPModel(provider=provider)

    messages: list[Any] = [
        ModelRequest(parts=[UserPromptPart(content="first turn")]),
        ModelResponse(parts=[TextPart(content="assistant reply")]),
        ModelRequest(parts=[UserPromptPart(content="second turn")]),
    ]

    response = asyncio.run(model.request(messages, None, ModelRequestParameters()))

    assert isinstance(response, ModelResponse)
    assert response.parts == [TextPart(content="ack")]
    assert response.model_name == "agent"
    sent_prompt = client.prompt_calls[0]["prompt"]
    assert len(sent_prompt) == 1
    assert sent_prompt[0].text == "second turn"


def test_request_with_full_history_mode_serializes_the_entire_conversation() -> None:
    client = FakeACPClient(prompt_response={"text": "ack"})
    provider = ACPProvider(client=client)
    model = ACPModel(provider=provider, history_mode="full")

    messages: list[Any] = [
        ModelRequest(parts=[UserPromptPart(content="first turn")]),
        ModelResponse(parts=[TextPart(content="assistant reply")]),
    ]

    asyncio.run(model.request(messages, None, ModelRequestParameters()))

    sent_text = client.prompt_calls[0]["prompt"][0].text
    assert "<user>" in sent_text and "first turn" in sent_text
    assert "<assistant>" in sent_text and "assistant reply" in sent_text


def test_request_raises_when_function_tools_are_requested() -> None:
    provider = ACPProvider(client=FakeACPClient())
    model = ACPModel(provider=provider)
    params = ModelRequestParameters(function_tools=[ToolDefinition(name="echo")])

    with pytest.raises(NotImplementedError, match="function_tools"):
        asyncio.run(
            model.request([ModelRequest(parts=[UserPromptPart(content="hi")])], None, params)
        )


def test_request_raises_when_output_tools_are_requested() -> None:
    provider = ACPProvider(client=FakeACPClient())
    model = ACPModel(provider=provider)
    params = ModelRequestParameters()
    object.__setattr__(params, "output_tools", [ToolDefinition(name="out")])

    with pytest.raises(NotImplementedError, match="output_tools"):
        asyncio.run(
            model.request([ModelRequest(parts=[UserPromptPart(content="hi")])], None, params)
        )


def test_request_raises_when_native_tools_are_requested() -> None:
    provider = ACPProvider(client=FakeACPClient())
    model = ACPModel(provider=provider)
    params = ModelRequestParameters()
    object.__setattr__(params, "native_tools", [ToolDefinition(name="native")])

    with pytest.raises(NotImplementedError, match="native_tools"):
        asyncio.run(
            model.request([ModelRequest(parts=[UserPromptPart(content="hi")])], None, params)
        )


def test_request_raises_when_allow_text_output_is_false() -> None:
    provider = ACPProvider(client=FakeACPClient())
    model = ACPModel(provider=provider)
    params = ModelRequestParameters()
    object.__setattr__(params, "allow_text_output", False)

    with pytest.raises(NotImplementedError, match="allow_text_output=False"):
        asyncio.run(
            model.request([ModelRequest(parts=[UserPromptPart(content="hi")])], None, params)
        )


# ---------------------------------------------------------------------------
# Integration: ACPModel driven through a real ACP agent (no client.py mocks).
#
# This exercises the full path (ACPModel -> ACPProvider -> _DirectACPConnection
# -> a real `pydantic_acp` ACP agent) without touching any pydantic-ai or acp
# library internals, matching prior (pre-existing) adapter behavior.
# ---------------------------------------------------------------------------


def test_acp_model_round_trips_through_a_real_acp_agent(tmp_path: Path) -> None:
    adapter = create_acp_agent(
        agent=Agent(TestModel(custom_output_text="hello from acp")),
        config=AdapterConfig(session_store=MemorySessionStore()),
    )
    provider = ACPProvider.from_agent(adapter, cwd=str(tmp_path))
    model = ACPModel(provider=provider)

    response = asyncio.run(
        model.request(
            [ModelRequest(parts=[UserPromptPart(content="Hi there")])],
            None,
            ModelRequestParameters(),
        )
    )

    assert isinstance(response, ModelResponse)
    assert response.parts == [TextPart(content="hello from acp")]
    assert provider.session_id is not None

    asyncio.run(provider.close())
    assert provider.session_id is None