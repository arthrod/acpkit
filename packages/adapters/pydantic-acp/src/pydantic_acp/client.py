from __future__ import annotations as _annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, Protocol, TypeAlias, cast
from uuid import uuid4

from acp import PROTOCOL_VERSION
from acp.interfaces import Agent as ACPAgent
from acp.schema import (
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SseMcpServer,
    TextContentBlock,
)
from pydantic_ai import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model, ModelRequestParameters, check_allow_model_requests
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers import Provider
from pydantic_ai.settings import ModelSettings

ACPPromptBlock: TypeAlias = (
    TextContentBlock
    | ImageContentBlock
    | AudioContentBlock
    | ResourceContentBlock
    | EmbeddedResourceContentBlock
)
ACPServerDefinition: TypeAlias = HttpMcpServer | McpServerStdio | SseMcpServer
HistoryMode: TypeAlias = Literal["latest_user", "full"]
PermissionHandler: TypeAlias = Callable[..., Any | Awaitable[Any]]

__all__ = (
    "ACPClientConnection",
    "ACPModel",
    "ACPProvider",
    "ACPPromptBlock",
    "ACPServerDefinition",
    "HistoryMode",
)


class ACPClientConnection(Protocol):
    """Minimal ACP client-side connection needed by the Pydantic AI provider."""

    async def initialize(
        self,
        *,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[ACPServerDefinition] | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def prompt(
        self,
        *,
        prompt: list[ACPPromptBlock],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def cancel(self, session_id: str, **kwargs: Any) -> None: ...

    async def close_session(self, session_id: str, **kwargs: Any) -> Any: ...


class _UnconfiguredACPClient:
    async def initialize(self, **_: Any) -> Any:
        raise RuntimeError("ACPProvider has no ACP client connection configured.")

    async def new_session(self, *_: Any, **__: Any) -> Any:
        raise RuntimeError("ACPProvider has no ACP client connection configured.")

    async def prompt(self, *_: Any, **__: Any) -> Any:
        raise RuntimeError("ACPProvider has no ACP client connection configured.")

    async def cancel(self, *_: Any, **__: Any) -> None:
        raise RuntimeError("ACPProvider has no ACP client connection configured.")

    async def close_session(self, *_: Any, **__: Any) -> Any:
        raise RuntimeError("ACPProvider has no ACP client connection configured.")


class _DirectACPConnection:
    def __init__(self, agent: ACPAgent, host_client: ACPProvider) -> None:
        self._agent: ACPAgent = agent
        agent.on_connect(host_client)

    async def initialize(
        self,
        *,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self._agent.initialize(
            protocol_version=protocol_version,
            client_capabilities=client_capabilities,
            client_info=client_info,
            **kwargs,
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[ACPServerDefinition] | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self._agent.new_session(cwd=cwd, mcp_servers=mcp_servers, **kwargs)

    async def prompt(
        self,
        *,
        prompt: list[ACPPromptBlock],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self._agent.prompt(
            prompt=prompt,
            session_id=session_id,
            message_id=message_id,
            **kwargs,
        )

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        await self._agent.cancel(session_id=session_id, **kwargs)

    async def close_session(self, session_id: str, **kwargs: Any) -> Any:
        close_session = getattr(self._agent, "close_session", None)
        if close_session is None:
            return None
        return await close_session(session_id=session_id, **kwargs)


class ACPProvider(Provider[ACPClientConnection]):
    """Pydantic AI provider that treats an ACP agent/session as the remote API.

    The provider is intentionally the ACP boundary. It owns the ACP client-side
    connection, an ACP session id, and the ACP host-client callback surface used
    by ACP servers to stream updates. `ACPModel` is the corresponding Pydantic AI
    `Model` that delegates requests to this provider.
    """

    def __init__(
        self,
        client: ACPClientConnection | None = None,
        *,
        name: str = "acp",
        base_url: str = "acp://local",
        cwd: str = ".",
        session_id: str | None = None,
        mcp_servers: Sequence[ACPServerDefinition] | None = None,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        protocol_version: int = PROTOCOL_VERSION,
        permission_handler: PermissionHandler | None = None,
    ) -> None:
        self._client: ACPClientConnection = client or cast(ACPClientConnection, _UnconfiguredACPClient())
        self._name: str = name
        self._base_url: str = base_url
        self._cwd: str = cwd
        self._session_id: str | None = session_id
        self._mcp_servers: list[ACPServerDefinition] | None = (
            list(mcp_servers) if mcp_servers is not None else None
        )
        self._client_capabilities: ClientCapabilities = client_capabilities or ClientCapabilities()
        self._client_info: Implementation = client_info or Implementation(
            name="pydantic-acp", version="2"
        )
        self._protocol_version: int = protocol_version
        self._permission_handler: PermissionHandler | None = permission_handler
        self._initialized: bool = False
        self._lifecycle_lock: asyncio.Lock = asyncio.Lock()
        self._prompt_locks: dict[str, asyncio.Lock] = {}
        self._active_text: dict[str, list[str]] = {}
        self._updates: list[tuple[str, Any, dict[str, Any]]] = []

    @classmethod
    def from_agent(
        cls,
        agent: ACPAgent,
        **kwargs: Any,
    ) -> ACPProvider:
        """Create a provider around an in-process ACP agent."""
        provider = cls(client=None, **kwargs)
        provider._client = _DirectACPConnection(agent, provider)
        return provider

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def client(self) -> ACPClientConnection:
        return self._client

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def updates(self) -> tuple[tuple[str, Any, dict[str, Any]], ...]:
        return tuple(self._updates)

    @staticmethod
    def model_profile(model_name: str) -> ModelProfile | None:
        del model_name
        return None

    async def __aenter__(self) -> ACPProvider:
        await self.ensure_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool | None:
        del exc_type, exc_val, exc_tb
        await self.close()
        return None

    async def ensure_session(self) -> str:
        async with self._lifecycle_lock:
            if not self._initialized:
                await self._client.initialize(
                    protocol_version=self._protocol_version,
                    client_capabilities=self._client_capabilities,
                    client_info=self._client_info,
                )
                self._initialized = True
            if self._session_id is None:
                response = await self._client.new_session(
                    cwd=self._cwd,
                    mcp_servers=self._mcp_servers,
                )
                self._session_id = _response_field(response, "session_id", "sessionId")
                if self._session_id is None:
                    raise RuntimeError("ACP new_session response did not include a session id.")
            return self._session_id

    async def close(self) -> None:
        session_id = self._session_id
        if session_id is None:
            return
        self._session_id = None
        close_session = getattr(self._client, "close_session", None)
        if close_session is not None:
            await close_session(session_id=session_id)

    async def prompt_text(
        self,
        prompt: list[ACPPromptBlock],
        *,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        session_id = await self.ensure_session()
        lock = self._prompt_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            self._active_text[session_id] = []
            try:
                response = await self._client.prompt(
                    prompt=prompt,
                    session_id=session_id,
                    message_id=message_id,
                    **kwargs,
                )
                streamed_text = "".join(self._active_text.get(session_id, ()))
                if streamed_text:
                    return streamed_text
                response_text = _extract_response_text(response)
                if response_text:
                    return response_text
                return ""
            finally:
                self._active_text.pop(session_id, None)

    async def cancel(self) -> None:
        session_id = self._session_id
        if session_id is not None:
            await self._client.cancel(session_id=session_id)

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        self._updates.append((session_id, update, dict(kwargs)))
        text = _extract_update_text(update)
        if text:
            self._active_text.setdefault(session_id, []).append(text)

    async def request_permission(
        self,
        options: list[Any],
        session_id: str,
        tool_call: Any,
        **kwargs: Any,
    ) -> Any:
        if self._permission_handler is None:
            raise PermissionError(
                "ACPProvider cannot grant ACP tool permissions without a permission_handler."
            )
        result: Any | Awaitable[Any] = self._permission_handler(
            options=options,
            session_id=session_id,
            tool_call=tool_call,
            **kwargs,
        )
        if inspect.isawaitable(result):
            return await result
        return result

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        del params
        raise NotImplementedError(f"Unsupported ACP extension method: {method}")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        del method, params


class ACPModel(Model[ACPClientConnection]):
    """Pydantic AI model facade for an ACP agent.

    ACP sessions are already agent-like and stateful. By default, each model
    request sends only the latest user turn to the ACP session; set
    `history_mode="full"` to serialize the whole Pydantic AI message history.
    """

    def __init__(
        self,
        model_name: str = "agent",
        *,
        provider: ACPProvider,
        history_mode: HistoryMode = "latest_user",
        settings: ModelSettings | None = None,
        profile: Any = None,
    ) -> None:
        super().__init__(settings=settings, profile=profile)
        self._model_name: str = model_name
        self._provider: ACPProvider = provider
        self._history_mode: HistoryMode = history_mode

    @property
    def provider(self) -> ACPProvider:
        return self._provider

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system(self) -> str:
        return self.provider.name

    @property
    def base_url(self) -> str | None:
        return self.provider.base_url

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        check_allow_model_requests()
        self._raise_for_unsupported_request_parameters(model_request_parameters)
        _model_settings, model_request_parameters = self.prepare_request(
            model_settings,
            model_request_parameters,
        )
        del _model_settings
        self._raise_for_unsupported_request_parameters(model_request_parameters)
        prompt_text = _render_prompt_text(messages, history_mode=self._history_mode)
        output_text = await self.provider.prompt_text(
            [TextContentBlock(type="text", text=prompt_text)],
            message_id=uuid4().hex,
        )
        return ModelResponse(
            parts=[TextPart(content=output_text)],
            model_name=self.model_name,
        )

    def _raise_for_unsupported_request_parameters(
        self,
        model_request_parameters: ModelRequestParameters,
    ) -> None:
        unsupported: list[str] = []
        for name in ("function_tools", "output_tools", "native_tools"):
            value = getattr(model_request_parameters, name, None)
            if value:
                unsupported.append(name)
        if getattr(model_request_parameters, "allow_text_output", True) is False:
            unsupported.append("allow_text_output=False")
        if unsupported:
            joined = ", ".join(unsupported)
            raise NotImplementedError(
                "ACPModel wraps an ACP agent/session as a Pydantic AI model. "
                "Register tools, native tools, and structured-output behavior on the "
                f"ACP-side agent instead of passing them through the model ({joined})."
            )


def _response_field(response: Any, *names: str) -> Any:
    for name in names:
        if isinstance(response, dict) and name in response:
            return response[name]
        if hasattr(response, name):
            return getattr(response, name)
    return None


def _extract_update_text(update: Any) -> str:
    parts: list[str] = []
    for candidate in _walk_text_candidates(update):
        if isinstance(candidate, str):
            parts.append(candidate)
    return "".join(parts)


def _extract_response_text(response: Any) -> str:
    if response is None:
        return ""
    parts: list[str] = []
    for name in ("text", "output_text", "content", "message"):
        value = _response_field(response, name)
        if isinstance(value, str):
            parts.append(value)
    return "".join(parts)


def _walk_text_candidates(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, TextContentBlock):
        return [value.text]
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        items: list[Any] = []
        for item in value:
            items.extend(_walk_text_candidates(item))
        return items

    candidates: list[Any] = []
    content = getattr(value, "content", None)
    if content is not None and content is not value:
        candidates.extend(_walk_text_candidates(content))
    for name in ("text", "delta", "message", "output_text"):
        attr = getattr(value, name, None)
        if isinstance(attr, str):
            candidates.append(attr)
    return candidates


def _render_prompt_text(messages: list[ModelMessage], *, history_mode: HistoryMode) -> str:
    if history_mode == "latest_user":
        latest = _latest_model_request(messages)
        if latest is not None:
            text = _render_message(latest, include_role=False)
            if text.strip():
                return text
    return "\n\n".join(_render_message(message, include_role=True) for message in messages).strip()


def _latest_model_request(messages: list[ModelMessage]) -> Any | None:
    for message in reversed(messages):
        if type(message).__name__ == "ModelRequest":
            return message
    return messages[-1] if messages else None


def _render_message(message: Any, *, include_role: bool) -> str:
    parts = getattr(message, "parts", None)
    if not isinstance(parts, Sequence):
        text = _stringify_content(message)
    else:
        rendered_parts = [_render_part(part) for part in parts]
        text = "\n".join(part for part in rendered_parts if part).strip()
    if not include_role:
        return text
    role = "assistant" if type(message).__name__ == "ModelResponse" else "user"
    return f"<{role}>\n{text}\n</{role}>"


def _render_part(part: Any) -> str:
    part_type = type(part).__name__
    if part_type == "SystemPromptPart":
        return f"<system>{_stringify_content(part)}</system>"
    if part_type == "ToolCallPart":
        tool_name = getattr(part, "tool_name", "tool")
        args = getattr(part, "args", None)
        return f"[tool-call:{tool_name}] {args!r}"
    if part_type in {"ToolReturnPart", "RetryPromptPart"}:
        tool_call_id = getattr(part, "tool_call_id", "")
        return f"[tool-result:{tool_call_id}] {_stringify_content(part)}".strip()
    return _stringify_content(part)


def _stringify_content(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, bytes | bytearray | str):
        return "\n".join(_stringify_content(item) for item in content)
    if hasattr(content, "data") or type(content).__name__.lower().find("image") >= 0:
        return f"[{type(content).__name__}]"
    if content is None:
        return ""
    return str(content)
