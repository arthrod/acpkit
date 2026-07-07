from __future__ import annotations as _annotations

import asyncio
from typing import Any

import pytest
from acp import PROTOCOL_VERSION
from acp.helpers import text_block
from acp.schema import AgentMessageChunk, ClientCapabilities, Implementation, TextContentBlock
from pydantic_ai import ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import SystemPromptPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition

from pydantic_acp.client import (
    ACPModel,
    ACPProvider,
    _extract_response_text,
    _extract_update_text,
    _response_field,
)

# ---------------------------------------------------------------------------
# Transport-layer fakes.
#
# These fakes stand in for the wire-level ACP client connection (FakeTransportClient)
# and for an in-process ACP agent (FakeACPAgentServer). They implement the same
# duck-typed surface the real `acp` library objects expose, so ACPProvider and
# ACPModel are exercised exactly as they would be in production. Nothing here
# patches methods on real library classes.
# ---------------------------------------------------------------------------


class FakeTransportClient:
    """Fake remote ACP client-side connection used in place of a real wire transport."""

    def __init__(
        self,
        *,
        session_id: str = "session-1",
        new_session_response: Any = None,
        prompt_response: Any = None,
        stream_events: Any = (),
    ) -> None:
        self.host: ACPProvider | None = None
        self.initialize_calls: list[dict[str, Any]] = []
        self.new_session_calls: list[dict[str, Any]] = []
        self.prompt_calls: list[dict[str, Any]] = []
        self.cancel_calls: list[str] = []
        self.close_session_calls: list[str] = []
        self._session_id = session_id
        self._new_session_response = new_session_response
        self._prompt_response = prompt_response
        self._stream_events = list(stream_events)

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
        return None

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self.new_session_calls.append({"cwd": cwd, "mcp_servers": mcp_servers, **kwargs})
        if self._new_session_response is not None:
            return self._new_session_response
        return {"session_id": self._session_id}

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
        if self.host is not None:
            for event in self._stream_events:
                await self.host.session_update(session_id, event)
        return self._prompt_response

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        del kwargs
        self.cancel_calls.append(session_id)

    async def close_session(self, session_id: str, **kwargs: Any) -> Any:
        del kwargs
        self.close_session_calls.append(session_id)
        return None


class FakeACPAgentServer:
    """Fake in-process ACP agent used to exercise `ACPProvider.from_agent`."""

    def __init__(
        self,
        *,
        session_id: str = "session-1",
        prompt_response: Any = None,
        stream_events: Any = (),
    ) -> None:
        self.host_client: Any = None
        self.initialize_calls: list[dict[str, Any]] = []
        self.new_session_calls: list[dict[str, Any]] = []
        self.prompt_calls: list[dict[str, Any]] = []
        self.cancel_calls: list[str] = []
        self.close_session_calls: list[str] = []
        self._session_id = session_id
        self._prompt_response = prompt_response
        self._stream_events = list(stream_events)

    def on_connect(self, conn: Any) -> None:
        self.host_client = conn

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
        return None

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self.new_session_calls.append({"cwd": cwd, "mcp_servers": mcp_servers, **kwargs})
        return {"session_id": self._session_id}

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
        if self.host_client is not None:
            for event in self._stream_events:
                await self.host_client.session_update(session_id, event)
        return self._prompt_response

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        del kwargs
        self.cancel_calls.append(session_id)

    async def close_session(self, session_id: str, **kwargs: Any) -> Any:
        del kwargs
        self.close_session_calls.append(session_id)
        return None


class FakeACPAgentServerWithoutCloseSession(FakeACPAgentServer):
    """Variant with no `close_session` support, matching older/minimal ACP agents."""

    close_session = None


def _agent_message(text: str) -> AgentMessageChunk:
    return AgentMessageChunk(session_update="agent_message_chunk", content=text_block(text))


# ---------------------------------------------------------------------------
# ACPProvider: session lifecycle.
# ---------------------------------------------------------------------------


def test_ensure_session_initializes_client_and_creates_session() -> None:
    client = FakeTransportClient(session_id="session-abc")
    provider = ACPProvider(client=client, cwd="/workspace")

    session_id = asyncio.run(provider.ensure_session())

    assert session_id == "session-abc"
    assert provider.session_id == "session-abc"
    assert len(client.initialize_calls) == 1
    assert client.initialize_calls[0]["protocol_version"] == PROTOCOL_VERSION
    assert len(client.new_session_calls) == 1
    assert client.new_session_calls[0]["cwd"] == "/workspace"


def test_ensure_session_is_idempotent_and_only_initializes_once() -> None:
    client = FakeTransportClient()
    provider = ACPProvider(client=client)

    first = asyncio.run(provider.ensure_session())
    second = asyncio.run(provider.ensure_session())

    assert first == second == "session-1"
    assert len(client.initialize_calls) == 1
    assert len(client.new_session_calls) == 1


def test_ensure_session_with_preset_session_id_skips_new_session_but_still_initializes() -> None:
    client = FakeTransportClient()
    provider = ACPProvider(client=client, session_id="preset-session")

    session_id = asyncio.run(provider.ensure_session())

    assert session_id == "preset-session"
    assert len(client.initialize_calls) == 1
    assert client.new_session_calls == []


def test_ensure_session_raises_when_new_session_response_lacks_session_id() -> None:
    client = FakeTransportClient(new_session_response={})
    provider = ACPProvider(client=client)

    with pytest.raises(RuntimeError, match="did not include a session id"):
        asyncio.run(provider.ensure_session())


def test_ensure_session_accepts_camel_case_session_id_field() -> None:
    client = FakeTransportClient(new_session_response={"sessionId": "camel-session"})
    provider = ACPProvider(client=client)

    session_id = asyncio.run(provider.ensure_session())

    assert session_id == "camel-session"


def test_close_closes_active_session_and_resets_session_id() -> None:
    client = FakeTransportClient(session_id="session-to-close")
    provider = ACPProvider(client=client)
    asyncio.run(provider.ensure_session())

    asyncio.run(provider.close())

    assert provider.session_id is None
    assert client.close_session_calls == ["session-to-close"]


def test_close_without_active_session_is_a_noop() -> None:
    client = FakeTransportClient()
    provider = ACPProvider(client=client)

    asyncio.run(provider.close())

    assert client.close_session_calls == []


async def _run_context_manager(provider: ACPProvider) -> str | None:
    async with provider as entered:
        assert entered is provider
        return provider.session_id


def test_async_context_manager_opens_and_closes_session() -> None:
    client = FakeTransportClient(session_id="ctx-session")
    provider = ACPProvider(client=client)

    session_id_inside = asyncio.run(_run_context_manager(provider))

    assert session_id_inside == "ctx-session"
    assert provider.session_id is None
    assert client.close_session_calls == ["ctx-session"]


def test_unconfigured_provider_raises_runtime_error_on_ensure_session() -> None:
    provider = ACPProvider()

    with pytest.raises(RuntimeError, match="no ACP client connection configured"):
        asyncio.run(provider.ensure_session())


# ---------------------------------------------------------------------------
# ACPProvider: prompt_text.
# ---------------------------------------------------------------------------


def test_prompt_text_prefers_streamed_updates_over_response_payload() -> None:
    client = FakeTransportClient(
        stream_events=[_agent_message("Hello"), _agent_message(" world")],
        prompt_response={"text": "ignored fallback text"},
    )
    provider = ACPProvider(client=client)
    client.host = provider

    result = asyncio.run(provider.prompt_text([text_block("hi")]))

    assert result == "Hello world"


def test_prompt_text_falls_back_to_response_payload_without_streaming() -> None:
    client = FakeTransportClient(prompt_response={"text": "response text"})
    provider = ACPProvider(client=client)
    client.host = provider

    result = asyncio.run(provider.prompt_text([text_block("hi")]))

    assert result == "response text"


def test_prompt_text_returns_empty_string_when_no_text_is_available() -> None:
    client = FakeTransportClient(prompt_response={"stop_reason": "end_turn"})
    provider = ACPProvider(client=client)
    client.host = provider

    result = asyncio.run(provider.prompt_text([text_block("hi")]))

    assert result == ""


def test_prompt_text_clears_active_text_buffer_between_calls() -> None:
    client = FakeTransportClient(stream_events=[_agent_message("first call")])
    provider = ACPProvider(client=client)
    client.host = provider

    first_result = asyncio.run(provider.prompt_text([text_block("hi")]))
    client._stream_events = []
    client._prompt_response = {"text": "second call fallback"}
    second_result = asyncio.run(provider.prompt_text([text_block("hi again")]))

    assert first_result == "first call"
    assert second_result == "second call fallback"


def test_prompt_text_forwards_prompt_blocks_and_message_id_to_client() -> None:
    client = FakeTransportClient()
    provider = ACPProvider(client=client)
    client.host = provider
    blocks = [text_block("payload")]

    asyncio.run(provider.prompt_text(blocks, message_id="msg-42"))

    assert client.prompt_calls[0]["prompt"] == blocks
    assert client.prompt_calls[0]["message_id"] == "msg-42"
    assert client.prompt_calls[0]["session_id"] == provider.session_id


# ---------------------------------------------------------------------------
# ACPProvider: cancel.
# ---------------------------------------------------------------------------


def test_cancel_forwards_to_client_when_session_is_active() -> None:
    client = FakeTransportClient(session_id="cancel-session")
    provider = ACPProvider(client=client)
    asyncio.run(provider.ensure_session())

    asyncio.run(provider.cancel())

    assert client.cancel_calls == ["cancel-session"]


def test_cancel_without_active_session_is_a_noop() -> None:
    client = FakeTransportClient()
    provider = ACPProvider(client=client)

    asyncio.run(provider.cancel())

    assert client.cancel_calls == []


# ---------------------------------------------------------------------------
# ACPProvider: session_update / updates recording.
# ---------------------------------------------------------------------------


def test_session_update_records_updates_and_exposes_an_immutable_snapshot() -> None:
    provider = ACPProvider()
    update = _agent_message("hi")

    asyncio.run(provider.session_update("session-x", update, extra="value"))

    assert provider.updates == (("session-x", update, {"extra": "value"}),)
    with pytest.raises(AttributeError):
        provider.updates.append(("nope", None, {}))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ACPProvider: request_permission.
# ---------------------------------------------------------------------------


def test_request_permission_without_handler_raises_permission_error() -> None:
    provider = ACPProvider()

    with pytest.raises(PermissionError, match="permission_handler"):
        asyncio.run(provider.request_permission([], "session-1", tool_call=None))


def test_request_permission_invokes_sync_handler_and_returns_its_result() -> None:
    calls: list[dict[str, Any]] = []

    def handler(*, options: Any, session_id: str, tool_call: Any, **kwargs: Any) -> Any:
        calls.append({"options": options, "session_id": session_id, "tool_call": tool_call, **kwargs})
        return "sync-result"

    provider = ACPProvider(permission_handler=handler)

    result = asyncio.run(
        provider.request_permission(["opt-a"], "session-1", tool_call="tool-call-1", note="n")
    )

    assert result == "sync-result"
    assert calls == [
        {"options": ["opt-a"], "session_id": "session-1", "tool_call": "tool-call-1", "note": "n"}
    ]


def test_request_permission_invokes_async_handler_and_awaits_its_result() -> None:
    async def handler(*, options: Any, session_id: str, tool_call: Any, **kwargs: Any) -> Any:
        del options, session_id, tool_call, kwargs
        return "async-result"

    provider = ACPProvider(permission_handler=handler)

    result = asyncio.run(provider.request_permission([], "session-1", tool_call=None))

    assert result == "async-result"


# ---------------------------------------------------------------------------
# ACPProvider: ext_method / ext_notification.
# ---------------------------------------------------------------------------


def test_ext_method_raises_not_implemented_error() -> None:
    provider = ACPProvider()

    with pytest.raises(NotImplementedError, match="unsupported/method"):
        asyncio.run(provider.ext_method("unsupported/method", {"a": 1}))


def test_ext_notification_is_a_noop() -> None:
    provider = ACPProvider()

    asyncio.run(provider.ext_notification("some/notification", {"a": 1}))


# ---------------------------------------------------------------------------
# ACPProvider.from_agent / _DirectACPConnection.
# ---------------------------------------------------------------------------


def test_from_agent_registers_provider_as_the_agents_host_client() -> None:
    agent = FakeACPAgentServer()

    provider = ACPProvider.from_agent(agent)

    assert agent.host_client is provider


def test_from_agent_ensure_session_delegates_directly_to_the_agent() -> None:
    agent = FakeACPAgentServer(session_id="direct-session")
    provider = ACPProvider.from_agent(agent, cwd="/direct")

    session_id = asyncio.run(provider.ensure_session())

    assert session_id == "direct-session"
    assert agent.new_session_calls[0]["cwd"] == "/direct"


def test_from_agent_prompt_text_collects_updates_streamed_from_the_agent() -> None:
    agent = FakeACPAgentServer(stream_events=[_agent_message("direct-agent-reply")])
    provider = ACPProvider.from_agent(agent)

    result = asyncio.run(provider.prompt_text([text_block("hi")]))

    assert result == "direct-agent-reply"
    assert agent.prompt_calls[0]["session_id"] == provider.session_id


def test_from_agent_close_delegates_to_agents_close_session() -> None:
    agent = FakeACPAgentServer(session_id="closeable-session")
    provider = ACPProvider.from_agent(agent)
    asyncio.run(provider.ensure_session())

    asyncio.run(provider.close())

    assert agent.close_session_calls == ["closeable-session"]


def test_from_agent_close_tolerates_agents_without_close_session_support() -> None:
    agent = FakeACPAgentServerWithoutCloseSession(session_id="no-close-session")
    provider = ACPProvider.from_agent(agent)
    asyncio.run(provider.ensure_session())

    asyncio.run(provider.close())

    assert provider.session_id is None


def test_from_agent_cancel_delegates_to_the_agent() -> None:
    agent = FakeACPAgentServer(session_id="cancel-direct")
    provider = ACPProvider.from_agent(agent)
    asyncio.run(provider.ensure_session())

    asyncio.run(provider.cancel())

    assert agent.cancel_calls == ["cancel-direct"]


# ---------------------------------------------------------------------------
# Module-level extraction helpers.
# ---------------------------------------------------------------------------


def test_response_field_reads_from_dict_and_object_by_first_matching_name() -> None:
    class Response:
        def __init__(self) -> None:
            self.sessionId = "obj-session"

    assert _response_field({"session_id": "dict-session"}, "session_id", "sessionId") == "dict-session"
    assert _response_field(Response(), "session_id", "sessionId") == "obj-session"
    assert _response_field({}, "session_id", "sessionId") is None
    assert _response_field(None, "session_id", "sessionId") is None


def test_extract_response_text_returns_empty_string_for_none_response() -> None:
    assert _extract_response_text(None) == ""


def test_extract_response_text_reads_known_text_fields() -> None:
    assert _extract_response_text({"text": "from-text-field"}) == "from-text-field"
    assert _extract_response_text({"output_text": "from-output-text"}) == "from-output-text"
    assert _extract_response_text({"stop_reason": "end_turn"}) == ""


def test_extract_update_text_reads_text_content_block_and_wrapped_chunks() -> None:
    assert _extract_update_text(text_block("plain block")) == "plain block"
    assert _extract_update_text(_agent_message("wrapped chunk")) == "wrapped chunk"
    assert _extract_update_text([text_block("a"), text_block("b")]) == "ab"
    assert _extract_update_text(None) == ""


# ---------------------------------------------------------------------------
# ACPModel.
# ---------------------------------------------------------------------------


def test_model_exposes_provider_backed_system_and_base_url() -> None:
    provider = ACPProvider(name="my-acp", base_url="acp://remote")
    model = ACPModel(provider=provider)

    assert model.system == "my-acp"
    assert model.base_url == "acp://remote"
    assert model.model_name == "agent"
    assert model.provider is provider


def test_request_with_latest_user_history_mode_sends_only_the_latest_user_turn() -> None:
    client = FakeTransportClient(prompt_response={"text": "final answer"})
    provider = ACPProvider(client=client)
    client.host = provider
    model = ACPModel(provider=provider)
    messages = [
        ModelRequest(parts=[UserPromptPart(content="first turn")]),
        ModelResponse(parts=[TextPart(content="assistant reply")]),
        ModelRequest(parts=[UserPromptPart(content="second turn")]),
    ]

    response = asyncio.run(model.request(messages, None, ModelRequestParameters()))

    assert isinstance(response, ModelResponse)
    assert response.parts == [TextPart(content="final answer")]
    assert response.model_name == "agent"
    sent_prompt = client.prompt_calls[0]["prompt"]
    assert sent_prompt == [TextContentBlock(type="text", text="second turn")]


def test_request_with_full_history_mode_renders_entire_message_history() -> None:
    client = FakeTransportClient(prompt_response={"text": "ok"})
    provider = ACPProvider(client=client)
    client.host = provider
    model = ACPModel(provider=provider, history_mode="full")
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart(content="be nice"),
                UserPromptPart(content="first turn"),
            ]
        ),
        ModelResponse(parts=[TextPart(content="assistant reply")]),
        ModelRequest(parts=[UserPromptPart(content="second turn")]),
    ]

    asyncio.run(model.request(messages, None, ModelRequestParameters()))

    rendered = client.prompt_calls[0]["prompt"][0].text
    assert "<system>be nice</system>" in rendered
    assert "<user>" in rendered and "first turn" in rendered
    assert "<assistant>" in rendered and "assistant reply" in rendered
    assert "second turn" in rendered


def test_request_renders_tool_calls_and_tool_returns_in_full_history_mode() -> None:
    client = FakeTransportClient(prompt_response={"text": "ok"})
    provider = ACPProvider(client=client)
    client.host = provider
    model = ACPModel(provider=provider, history_mode="full")
    messages = [
        ModelRequest(parts=[UserPromptPart(content="run the tool")]),
        ModelResponse(parts=[ToolCallPart(tool_name="lookup", args={"query": "acp"}, tool_call_id="call-1")]),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name="lookup", content="tool output", tool_call_id="call-1"),
            ]
        ),
    ]

    asyncio.run(model.request(messages, None, ModelRequestParameters()))

    rendered = client.prompt_calls[0]["prompt"][0].text
    assert "[tool-call:lookup]" in rendered
    assert "[tool-result:call-1]" in rendered
    assert "tool output" in rendered


def test_request_falls_back_to_full_history_when_latest_user_turn_is_empty() -> None:
    client = FakeTransportClient(prompt_response={"text": "ok"})
    provider = ACPProvider(client=client)
    client.host = provider
    model = ACPModel(provider=provider)
    messages = [ModelRequest(parts=[UserPromptPart(content="only turn")])]
    # No trailing ModelRequest at all: the "latest_user" lookup falls back to
    # rendering the entire (single-message) history, matching the same code
    # path exercised by history_mode="full".
    messages_without_request: list[Any] = [ModelResponse(parts=[TextPart(content="assistant only")])]

    asyncio.run(model.request(messages, None, ModelRequestParameters()))
    first_rendered = client.prompt_calls[0]["prompt"][0].text
    assert first_rendered == "only turn"

    asyncio.run(model.request(messages_without_request, None, ModelRequestParameters()))
    second_rendered = client.prompt_calls[1]["prompt"][0].text
    assert "assistant only" in second_rendered


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (
            {
                "function_tools": [
                    ToolDefinition(name="t", description="d", parameters_json_schema={"type": "object"})
                ]
            },
            "function_tools",
        ),
        (
            {
                "output_tools": [
                    ToolDefinition(name="t", description="d", parameters_json_schema={"type": "object"})
                ]
            },
            "output_tools",
        ),
        ({"allow_text_output": False}, "allow_text_output=False"),
    ],
)
def test_request_rejects_unsupported_request_parameters(kwargs: dict[str, Any], match: str) -> None:
    client = FakeTransportClient()
    provider = ACPProvider(client=client)
    client.host = provider
    model = ACPModel(provider=provider)
    messages = [ModelRequest(parts=[UserPromptPart(content="hi")])]

    with pytest.raises(NotImplementedError, match=match):
        asyncio.run(model.request(messages, None, ModelRequestParameters(**kwargs)))


def test_request_with_plain_parameters_and_no_tools_succeeds() -> None:
    """Regression check: the ordinary text-only request path (the behavior that
    existed before tool/output support was explicitly rejected) keeps working."""
    client = FakeTransportClient(prompt_response={"text": "plain response"})
    provider = ACPProvider(client=client)
    client.host = provider
    model = ACPModel(provider=provider)
    messages = [ModelRequest(parts=[UserPromptPart(content="hi")])]

    response = asyncio.run(model.request(messages, None, ModelRequestParameters()))

    assert response.parts == [TextPart(content="plain response")]