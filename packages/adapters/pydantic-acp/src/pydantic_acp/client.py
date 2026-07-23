from __future__ import annotations as _annotations

import asyncio
import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast
from uuid import uuid4

from acp import PROTOCOL_VERSION
from acp.exceptions import RequestError
from acp.helpers import text_block
from acp.interfaces import Agent as AcpAgent
from acp.interfaces import Client as AcpClient
from acp.schema import (
    AgentMessageChunk,
    ClientCapabilities,
    CreateTerminalResponse,
    EnvVariable,
    Implementation,
    KillTerminalResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    TerminalOutputResponse,
    ToolCallUpdate,
    UsageUpdate,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    AudioUrl,
    BinaryContent,
    DocumentUrl,
    FinishReason,
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponseStreamEvent,
    RetryPromptPart,
    SystemPromptPart,
    TextContent,
    TextPart,
    ToolReturnPart,
    UploadedFile,
    UserContent,
    UserPromptPart,
    VideoUrl,
)
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.native_tools import AbstractNativeTool
from pydantic_ai.profiles import ModelProfile, ModelProfileSpec
from pydantic_ai.providers import Provider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from ._version import __version__
from .types import AgentPromptBlock

HistoryMode: TypeAlias = Literal["latest_user", "full"]
_DEFAULT_MODEL_NAME = "agent"

AcpPromptRenderer: TypeAlias = Callable[
    [Sequence[ModelMessage], ModelRequestParameters],
    Sequence[AgentPromptBlock] | Awaitable[Sequence[AgentPromptBlock]],
]

ACP_MODEL_PROFILE: ModelProfile = ModelProfile(
    supports_tools=False,
    supports_json_schema_output=False,
    supports_json_object_output=False,
    supports_image_output=False,
    supported_native_tools=frozenset[type[AbstractNativeTool]](),
)

__all__ = (
    "ACP_MODEL_PROFILE",
    "AcpHostBridge",
    "AcpModel",
    "AcpPromptRenderer",
    "AcpProvider",
    "AcpUpdateRecord",
)


# ---------------------------------------------------------------------------
# AcpUpdateRecord
# ---------------------------------------------------------------------------


class AcpUpdateRecord:
    """A host-side ACP update observed while an ACP-backed model request runs."""

    __slots__ = ("session_id", "source", "update")

    def __init__(self, *, session_id: str, update: Any, source: str | None = None) -> None:
        self.session_id = session_id
        self.update = update
        self.source = source


# ---------------------------------------------------------------------------
# AcpHostBridge
# ---------------------------------------------------------------------------


class AcpHostBridge:
    """Minimal ACP host/client implementation used by :class:`AcpProvider`.

    ACP agents send their visible output to a connected ACP client via
    ``session_update``. Pydantic AI models, however, return a ``ModelResponse``.
    This bridge is the seam between the two contracts: it records ACP updates so
    ``AcpModel`` can fold agent message chunks back into Pydantic AI response
    parts, while optionally delegating real host operations to an upstream ACP
    client supplied by the caller.

    The bridge intentionally does not emulate a filesystem, terminal, approval
    UI, or extension namespace. When an ACP agent asks for such host operations
    and no delegate was supplied, the request fails explicitly instead of
    inventing host behavior that is not present.
    """

    def __init__(self, *, delegate: AcpClient | None = None) -> None:
        self.delegate = delegate
        self.updates: list[AcpUpdateRecord] = []

    def snapshot_index(self) -> int:
        """Return an index that can later be used to read only new updates."""
        return len(self.updates)

    def records_since(
        self,
        index: int,
        *,
        session_id: str | None = None,
    ) -> list[AcpUpdateRecord]:
        """Return recorded updates after ``index``, optionally scoped to a session."""
        records = self.updates[index:]
        if session_id is None:
            return list(records)
        return [record for record in records if record.session_id == session_id]

    def agent_message_text_since(self, index: int, *, session_id: str) -> str:
        """Concatenate ACP agent message chunks recorded after ``index``."""
        text_parts: list[str] = []
        for record in self.records_since(index, session_id=session_id):
            update = record.update
            if not _is_agent_message_chunk(update):
                continue
            content = getattr(update, "content", None)
            text = getattr(content, "text", None)
            if isinstance(text, str):
                text_parts.append(text)
        return "".join(text_parts)

    def usage_update_since(self, index: int, *, session_id: str) -> RequestUsage:
        """Collect the latest ACP usage update observed after ``index``."""
        usage = RequestUsage()
        for record in self.records_since(index, session_id=session_id):
            update = record.update
            if not isinstance(update, UsageUpdate):
                continue
            usage = _usage_from_acp(getattr(update, "usage", None))
        return usage

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        """Record an ACP update and optionally forward it to a real host client."""
        self.updates.append(
            AcpUpdateRecord(
                session_id=session_id,
                update=update,
                source=kwargs.get("source"),
            ),
        )
        if self.delegate is not None and hasattr(self.delegate, "session_update"):
            await self._call_delegate(
                "session_update",
                session_id=session_id,
                update=update,
                **kwargs,
            )

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        return await self._call_delegate(
            "request_permission",
            options=options,
            session_id=session_id,
            tool_call=tool_call,
            **kwargs,
        )

    async def write_text_file(
        self,
        content: str,
        path: str,
        session_id: str,
        **kwargs: Any,
    ) -> WriteTextFileResponse | None:
        return await self._call_delegate(
            "write_text_file",
            content=content,
            path=path,
            session_id=session_id,
            **kwargs,
        )

    async def read_text_file(
        self,
        path: str,
        session_id: str,
        limit: int | None = None,
        line: int | None = None,
        **kwargs: Any,
    ) -> ReadTextFileResponse:
        return await self._call_delegate(
            "read_text_file",
            path=path,
            session_id=session_id,
            limit=limit,
            line=line,
            **kwargs,
        )

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[EnvVariable] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        return await self._call_delegate(
            "create_terminal",
            command=command,
            session_id=session_id,
            args=args,
            cwd=cwd,
            env=env,
            output_byte_limit=output_byte_limit,
            **kwargs,
        )

    async def terminal_output(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> TerminalOutputResponse:
        return await self._call_delegate(
            "terminal_output",
            session_id=session_id,
            terminal_id=terminal_id,
            **kwargs,
        )

    async def release_terminal(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> ReleaseTerminalResponse | None:
        return await self._call_delegate(
            "release_terminal",
            session_id=session_id,
            terminal_id=terminal_id,
            **kwargs,
        )

    async def wait_for_terminal_exit(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> WaitForTerminalExitResponse:
        return await self._call_delegate(
            "wait_for_terminal_exit",
            session_id=session_id,
            terminal_id=terminal_id,
            **kwargs,
        )

    async def kill_terminal(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> KillTerminalResponse | None:
        return await self._call_delegate(
            "kill_terminal",
            session_id=session_id,
            terminal_id=terminal_id,
            **kwargs,
        )

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return await self._call_delegate("ext_method", method=method, params=params)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        if self.delegate is None or not hasattr(self.delegate, "ext_notification"):
            return
        await self._call_delegate("ext_notification", method=method, params=params)

    def on_connect(self, conn: AcpAgent) -> None:
        """Forward reverse connections to a delegate host client when it supports them."""
        delegate = self.delegate
        if delegate is not None and hasattr(delegate, "on_connect"):
            delegate.on_connect(conn)

    async def _call_delegate(self, method_name: str, *, required: bool = True, **kwargs: Any) -> Any:
        delegate = self.delegate
        method = getattr(delegate, method_name, None) if delegate is not None else None
        if method is None:
            if not required:
                return None
            raise RuntimeError(
                f"ACP agent requested host method {method_name!r}, but no host client delegate "
                "was supplied to AcpProvider.",
            )
        result = method(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


# ---------------------------------------------------------------------------
# Internal result type
# ---------------------------------------------------------------------------


class _AcpPromptResult:
    __slots__ = ("session_id", "stop_reason", "text", "usage")

    def __init__(
        self,
        *,
        text: str,
        usage: RequestUsage,
        stop_reason: str | None,
        session_id: str,
    ) -> None:
        self.text = text
        self.usage = usage
        self.stop_reason = stop_reason
        self.session_id = session_id


# ---------------------------------------------------------------------------
# AcpProvider
# ---------------------------------------------------------------------------


class AcpProvider(Provider[AcpAgent]):
    """Pydantic AI provider that treats an ACP agent as the model backend.

    This is the inverse of the normal ``pydantic-acp`` server adapter. The
    server adapter exposes a ``pydantic_ai.Agent`` through ACP. ``AcpProvider``
    consumes an existing ACP agent and makes it available to Pydantic AI as a
    provider/model pair, so application code can write ordinary Pydantic AI
    agents while delegating the underlying model turn to ACP.

    The provider owns ACP protocol/session setup, model selection handoff via
    ``set_session_model`` when the remote agent supports it, host/client update
    capture, and prompt rendering. It deliberately remains a provider rather
    than an alternate agent framework: Pydantic AI still owns the outer agent
    run, result validation, usage accumulation, and history shape.
    """

    _history_mode: HistoryMode

    def __init__(
        self,
        *,
        acp_agent: AcpAgent,
        host_client: AcpClient | None = None,
        cwd: str | Path = ".",
        name: str = "acp",
        base_url: str = "acp://local",
        protocol_version: int = PROTOCOL_VERSION,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        mcp_servers: Sequence[Any] | None = None,
        prompt_renderer: AcpPromptRenderer | None = None,
        history_mode: HistoryMode = "latest_user",
    ) -> None:
        """Create a new ACP provider.

        Args:
            acp_agent: The ACP agent to wrap as a Pydantic AI provider/model.
            host_client: Optional upstream :class:`AcpClient` to delegate real
                host operations to (file I/O, terminals, permissions, etc.).
            cwd: Working directory passed to the ACP session on creation.
            name: Provider name reported via :attr:`name`. Defaults to
                ``"acp"``.
            base_url: Base URL reported via :attr:`base_url`. Defaults to
                ``"acp://local"``.
            protocol_version: ACP protocol version used during
                ``initialize``. Defaults to :data:`acp.PROTOCOL_VERSION`.
            client_capabilities: ACP client capabilities sent during
                ``initialize``. Defaults to an empty
                :class:`~acp.schema.ClientCapabilities`.
            client_info: ACP implementation info sent during ``initialize``.
                Defaults to a ``pydantic-acp-client`` stub.
            mcp_servers: Optional list of MCP servers forwarded to
                ``new_session``.
            prompt_renderer: Custom callable that converts Pydantic AI
                messages into ACP prompt blocks. When ``None`` the built-in
                renderer is used.
            history_mode: Controls how previous messages are rendered into
                the ACP prompt. ``"latest_user"`` (default) sends only the
                latest user turn; ``"full"`` sends the entire conversation.

        """
        self._client = acp_agent

        self._host = AcpHostBridge(delegate=host_client)
        self._name = name
        self._base_url = base_url
        self._cwd = str(cwd)
        self._protocol_version = protocol_version
        self._client_capabilities = client_capabilities
        self._client_info = client_info or Implementation(
            name="pydantic-acp-client",
            version=__version__,
        )
        self._mcp_servers = list(mcp_servers or [])
        self._prompt_renderer = prompt_renderer
        self._history_mode = history_mode
        self._initialized = False
        self._session_id: str | None = None
        self._current_model_name: str | None = None
        self._session_lock: asyncio.Lock | None = None
        self._session_lock_loop: asyncio.AbstractEventLoop | None = None

        if hasattr(self._client, "on_connect"):
            self._client.on_connect(self._host)

    # -- Provider abstract interface ----------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def client(self) -> AcpAgent:
        return self._client

    @staticmethod
    def model_profile(model_name: str) -> ModelProfile | None:
        del model_name
        return ACP_MODEL_PROFILE

    # -- Additional public API ----------------------------------------------

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def host(self) -> AcpHostBridge:
        """The ACP host bridge connected to the wrapped ACP agent."""
        return self._host

    @property
    def updates(self) -> list[AcpUpdateRecord]:
        """All ACP updates recorded by the host bridge so far."""
        return list(self._host.updates)

    def model(
        self,
        model_name: str | None = None,
        *,
        settings: ModelSettings | None = None,
        profile: ModelProfileSpec | None = None,
        history_mode: HistoryMode | None = None,
    ) -> AcpModel:
        """Build an :class:`AcpModel` bound to this provider.

        When ``model_name`` is ``None``, the bridge does not call ACP
        ``session/set_model`` and leaves model selection to the wrapped agent's
        session default. The visible Pydantic AI model name remains ``"agent"``.
        """
        return AcpModel(
            model_name=model_name,
            provider=self,
            settings=settings,
            profile=profile,
            history_mode=history_mode,
        )

    async def render_prompt_blocks(
        self,
        messages: Sequence[ModelMessage],
        model_request_parameters: ModelRequestParameters,
        *,
        history_mode: HistoryMode | None = None,
    ) -> list[AgentPromptBlock]:
        """Render Pydantic AI model messages into ACP prompt blocks."""
        if self._prompt_renderer is None:
            return _default_render_prompt_blocks(
                messages,
                model_request_parameters,
                history_mode=history_mode or self._history_mode,
            )
        rendered = self._prompt_renderer(messages, model_request_parameters)
        if inspect.isawaitable(rendered):
            rendered = await rendered
        return list(cast(Sequence[AgentPromptBlock], rendered))

    async def request_prompt(
        self,
        *,
        model_name: str | None,
        prompt: Sequence[AgentPromptBlock],
    ) -> _AcpPromptResult:
        """Send one prompt turn to the ACP agent and collect its visible text."""
        session_id = await self._ensure_session(model_name=model_name)
        start_index = self._host.snapshot_index()
        prompt_response = await self._client.prompt(
            prompt=list(prompt),
            session_id=session_id,
            message_id=uuid4().hex,
        )
        text = self._host.agent_message_text_since(start_index, session_id=session_id)
        if not text:
            text = _extract_text(prompt_response)

        usage = _usage_from_acp(getattr(prompt_response, "usage", None))
        if not usage.has_values():
            usage = self._host.usage_update_since(start_index, session_id=session_id)
        stop_reason = getattr(prompt_response, "stop_reason", None) or getattr(
            prompt_response,
            "stopReason",
            None,
        )
        return _AcpPromptResult(
            text=text,
            usage=usage,
            stop_reason=stop_reason,
            session_id=session_id,
        )

    async def _ensure_session(self, *, model_name: str | None) -> str:
        async with self._get_session_lock():
            if not self._initialized:
                await self._client.initialize(
                    protocol_version=self._protocol_version,
                    client_capabilities=self._client_capabilities or ClientCapabilities(),
                    client_info=self._client_info,
                )
                self._initialized = True

            if self._session_id is None:
                session = await self._client.new_session(
                    cwd=self._cwd,
                    mcp_servers=list(self._mcp_servers),
                )
                self._session_id = session.session_id

            if model_name is None:
                return self._session_id

            if self._current_model_name == model_name:
                return self._session_id

            set_session_model = getattr(self._client, "set_session_model", None)
            if set_session_model is not None:
                try:
                    result = set_session_model(
                        model_id=model_name,
                        session_id=self._session_id,
                    )
                    if inspect.isawaitable(result):
                        await result
                    self._current_model_name = model_name
                except RequestError as exc:
                    if exc.code != -32601:
                        raise
                    if not (
                        (exc.data or {}).get("method") == "session/set_model"
                        or "session/set_model" in str(exc)
                    ):
                        raise
                    # Method not found - assume model was set during session creation
                    self._current_model_name = model_name
            else:
                # Method doesn't exist - assume model was set during session creation
                self._current_model_name = model_name

        return self._session_id

    def _get_session_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._session_lock is None or self._session_lock_loop is not loop:
            self._session_lock = asyncio.Lock()
            self._session_lock_loop = loop
        return self._session_lock


# ---------------------------------------------------------------------------
# AcpModel
# ---------------------------------------------------------------------------


class AcpModel(Model[AcpAgent]):
    """Pydantic AI ``Model`` backed by an ACP agent provider."""

    _provider: Provider[AcpAgent]
    _history_mode: HistoryMode | None
    _model_name: str | None

    def __init__(
        self,
        model_name: str | None = None,
        *,
        provider: AcpProvider,
        settings: ModelSettings | None = None,
        profile: ModelProfileSpec | None = None,
        history_mode: HistoryMode | None = None,
    ) -> None:
        self._model_name = model_name
        self._history_mode = history_mode
        self._provider = provider
        super().__init__(settings=settings, profile=profile or ACP_MODEL_PROFILE)

    @property
    def model_name(self) -> str:
        return self._model_name or _DEFAULT_MODEL_NAME

    @property
    def system(self) -> str:
        return self._provider.name

    @property
    def base_url(self) -> str:
        return self._provider.base_url

    @classmethod
    def supported_native_tools(cls) -> frozenset[type[AbstractNativeTool]]:
        return frozenset()

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        model_settings, model_request_parameters = self.prepare_request(
            model_settings,
            model_request_parameters,
        )
        del model_settings
        self._ensure_supported_request(model_request_parameters)
        provider = cast(AcpProvider, self._provider)
        prompt = await provider.render_prompt_blocks(
            messages,
            model_request_parameters,
            history_mode=self._history_mode,
        )
        acp_result = await provider.request_prompt(
            model_name=self._model_name,
            prompt=prompt,
        )
        parts = [TextPart(acp_result.text, provider_name=self.system)] if acp_result.text else []
        return ModelResponse(
            parts=parts,
            model_name=self.model_name,
            provider_name=self.system,
            provider_url=self.base_url,
            usage=acp_result.usage,
            finish_reason=_finish_reason_from_acp(acp_result.stop_reason),
            provider_details={"acp_session_id": acp_result.session_id},
        )

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: Any | None = None,
    ) -> AsyncGenerator[StreamedResponse, None]:
        response = await self.request(messages, model_settings, model_request_parameters)
        yield _AcpBufferedStreamedResponse(
            model_request_parameters=model_request_parameters,
            response=response,
        )

    def _ensure_supported_request(self, params: ModelRequestParameters) -> None:
        if params.function_tools:
            tool_names = ", ".join(tool.name for tool in params.function_tools)
            raise UserError(
                "AcpModel delegates a model turn to an ACP agent and cannot execute "
                f"Pydantic AI function tools directly: {tool_names}. Register tools on "
                "the ACP agent or provide them through an ACP host bridge instead.",
            )
        if params.native_tools:
            raise UserError(
                "AcpModel does not expose Pydantic AI native tools directly; use the "
                "ACP agent/provider side for native capabilities.",
            )
        if params.output_tools or not params.allow_text_output:
            raise UserError(
                "AcpModel is a text-response provider bridge. Structured/tool-only "
                "output must be implemented by the ACP agent or validated after the run.",
            )


# ---------------------------------------------------------------------------
# _AcpBufferedStreamedResponse
# ---------------------------------------------------------------------------


class _AcpBufferedStreamedResponse(StreamedResponse):
    __slots__ = (
        "_response",
        "_usage",
        "finish_reason",
        "provider_details",
        "provider_response_id",
    )

    def __init__(
        self,
        *,
        model_request_parameters: ModelRequestParameters,
        response: ModelResponse,
    ) -> None:
        super().__init__(model_request_parameters=model_request_parameters)
        self._response = response
        self._usage = response.usage
        self.provider_response_id = response.provider_response_id
        self.provider_details = response.provider_details
        self.finish_reason = response.finish_reason

    async def _get_event_iterator(
        self,
    ) -> AsyncGenerator[ModelResponseStreamEvent, None]:
        for part in self._response.parts:
            if not isinstance(part, TextPart):
                continue
            for event in self._parts_manager.handle_text_delta(
                vendor_part_id=part.id or "content",
                content=part.content,
            ):
                yield event

    async def close_stream(self) -> None:
        return None

    @property
    def model_name(self) -> str:
        return self._response.model_name or "acp"

    @property
    def provider_name(self) -> str | None:
        return self._response.provider_name

    @property
    def provider_url(self) -> str | None:
        return self._response.provider_url

    @property
    def timestamp(self) -> datetime:
        return self._response.timestamp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_render_prompt_blocks(
    messages: Sequence[ModelMessage],
    model_request_parameters: ModelRequestParameters,
    *,
    history_mode: HistoryMode = "latest_user",
) -> list[AgentPromptBlock]:
    del model_request_parameters
    if history_mode == "latest_user":
        latest = _latest_model_request(messages)
        if latest is not None:
            text = _render_message(latest, include_role=False)
            if text.strip():
                return [text_block(text)]
    if not messages:
        return []
    full_text = "\n\n".join(
        _render_message(message, include_role=True) for message in messages
    ).strip()
    return [text_block(full_text)] if full_text else []


def _latest_model_request(messages: Sequence[ModelMessage]) -> ModelMessage | None:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            return message
    return messages[-1] if messages else None


def _render_message(message: ModelMessage, *, include_role: bool) -> str:
    if isinstance(message, ModelRequest):
        text = _render_request_as_text(message)
    else:
        text = message.text or ""
    if not include_role or not text:
        return text
    role = "user" if isinstance(message, ModelRequest) else "assistant"
    return f"<{role}>\n{text}\n{role}>"


def _render_request_as_text(request: ModelRequest) -> str:
    rendered: list[str] = []
    if request.instructions:
        rendered.append(_section("Instructions", request.instructions))
    for part in request.parts:
        if isinstance(part, UserPromptPart):
            rendered.append(_render_user_prompt(part))
        elif isinstance(part, SystemPromptPart):
            rendered.append(_section("System", part.content))
        elif isinstance(part, ToolReturnPart):
            rendered.append(_render_tool_return(part))
        elif isinstance(part, RetryPromptPart):
            rendered.append(part.model_response())
    return "\n\n".join(item for item in rendered if item).strip()


def _render_user_prompt(part: UserPromptPart) -> str:
    return _render_user_content(part.content)


def _render_user_content(content: str | Sequence[UserContent]) -> str:
    if isinstance(content, str):
        return content
    rendered: list[str] = []
    for item in content:
        rendered.append(_render_user_content_item(item))
    return "\n\n".join(item for item in rendered if item)


def _render_user_content_item(item: UserContent) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, TextContent):
        return item.content
    if isinstance(item, BinaryContent):
        return f"[binary:{item.media_type}:{len(item.data)} bytes]"
    if isinstance(item, ImageUrl | AudioUrl | DocumentUrl | VideoUrl):
        return f"[{item.kind}:{item.url}]"
    if isinstance(item, UploadedFile):
        return f"[uploaded-file:{item.provider_name}:{item.file_id}]"
    kind = getattr(item, "kind", type(item).__name__)
    return f"[{kind}]"


def _render_tool_return(part: ToolReturnPart) -> str:
    label = part.tool_name or part.tool_call_id
    content = part.model_response_str()
    return _section(f"Tool result: {label}", content)


def _section(title: str, content: str) -> str:
    content = content.strip()
    if not content:
        return ""
    return f"{title}:\n{content}"


def _is_agent_message_chunk(update: Any) -> bool:
    return (
        isinstance(update, AgentMessageChunk)
        or getattr(update, "session_update", None) == "agent_message_chunk"
    )


def _usage_from_acp(value: Any) -> RequestUsage:
    if value is None:
        return RequestUsage()
    details: dict[str, int] = {}
    thought_tokens = _int_attr(value, "thought_tokens")
    if thought_tokens:
        details["reasoning_tokens"] = thought_tokens
    return RequestUsage(
        input_tokens=_int_attr(value, "input_tokens"),
        cache_write_tokens=_int_attr(value, "cached_write_tokens"),
        cache_read_tokens=_int_attr(value, "cached_read_tokens"),
        output_tokens=_int_attr(value, "output_tokens"),
        details=details,
    )


def _int_attr(value: Any, name: str) -> int:
    raw_value = getattr(value, name, 0) or 0
    return int(raw_value)


def _finish_reason_from_acp(stop_reason: str | None) -> FinishReason:
    if stop_reason in (None, "end_turn", "stop"):
        return "stop"
    if stop_reason in ("max_tokens", "length"):
        return "length"
    if stop_reason == "cancelled":
        return "error"
    return "stop"


_TEXT_FIELD_NAMES = ("text", "delta", "message", "output_text", "response", "data")


def _extract_text(value: Any) -> str:
    """Recursively collect text from an ACP response or session-update payload."""
    return "".join(
        candidate for candidate in _walk_text_candidates(value) if isinstance(candidate, str)
    )


def _walk_text_candidates(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, AgentMessageChunk):
        content = getattr(value, "content", None)
        text = getattr(content, "text", None)
        return [text] if isinstance(text, str) else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items: list[Any] = []
        for item in value:
            items.extend(_walk_text_candidates(item))
        return items
    candidates: list[Any] = []
    content = _response_field(value, "content")
    if content is not None and content is not value:
        candidates.extend(_walk_text_candidates(content))
    for name in _TEXT_FIELD_NAMES:
        attr = _response_field(value, name)
        if isinstance(attr, str):
            candidates.append(attr)
    return candidates


def _response_field(response: Any, *names: str) -> Any:
    for name in names:
        if isinstance(response, dict) and name in response:
            return response[name]
        if hasattr(response, name):
            return getattr(response, name)
    return None
