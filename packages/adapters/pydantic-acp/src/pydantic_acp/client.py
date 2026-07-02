from __future__ import annotations as _annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias
from uuid import uuid4

from acp import PROTOCOL_VERSION
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
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelResponse,
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
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers import Provider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from ._version import __version__
from .types import AgentPromptBlock

AcpPromptRenderer: TypeAlias = Callable[
    [Sequence[ModelMessage], ModelRequestParameters],
    Sequence[AgentPromptBlock] | Awaitable[Sequence[AgentPromptBlock]],
]

ACP_MODEL_PROFILE: ModelProfile = {
    "supports_tools": False,
    "supports_json_schema_output": False,
    "supports_json_object_output": False,
    "supports_image_output": False,
    "supported_native_tools": frozenset(),
}

__all__ = (
    "ACP_MODEL_PROFILE",
    "AcpHostBridge",
    "AcpModel",
    "AcpPromptRenderer",
    "AcpProvider",
    "AcpUpdateRecord",
)


@dataclass(slots=True, frozen=True, kw_only=True)
class AcpUpdateRecord:
    """A host-side ACP update observed while an ACP-backed model request runs."""

    session_id: str
    update: Any
    source: str | None = None


@dataclass(slots=True, kw_only=True)
class AcpHostBridge:
    """Minimal ACP host/client implementation used by :class:`AcpProvider`.

    ACP agents send their visible output to a connected ACP client via
    ``session_update``.  Pydantic AI models, however, return a ``ModelResponse``.
    This bridge is the seam between the two contracts: it records ACP updates so
    ``AcpModel`` can fold agent message chunks back into Pydantic AI response
    parts, while optionally delegating real host operations to an upstream ACP
    client supplied by the caller.

    The bridge intentionally does not emulate a filesystem, terminal, approval
    UI, or extension namespace.  When an ACP agent asks for such host operations
    and no delegate was supplied, the request fails explicitly instead of
    inventing host behavior that is not present.
    """

    delegate: AcpClient | None = None
    updates: list[AcpUpdateRecord] = field(default_factory=list)

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
            )
        )
        if self.delegate is not None and hasattr(self.delegate, "session_update"):
            await self._call_delegate("session_update", session_id=session_id, update=update, **kwargs)

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
            return None
        await self._call_delegate("ext_notification", method=method, params=params)

    def on_connect(self, conn: AcpAgent) -> None:
        """Forward reverse connections to a delegate host client when it supports them."""
        if self.delegate is not None and hasattr(self.delegate, "on_connect"):
            self.delegate.on_connect(conn)

    async def _call_delegate(self, method_name: str, **kwargs: Any) -> Any:
        delegate = self.delegate
        method = getattr(delegate, method_name, None) if delegate is not None else None
        if method is None:
            raise RuntimeError(
                f"ACP agent requested host method {method_name!r}, but no host client delegate "
                "was supplied to AcpProvider."
            )
        result = method(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


@dataclass(slots=True, frozen=True, kw_only=True)
class _AcpPromptResult:
    text: str
    usage: RequestUsage
    stop_reason: str | None
    session_id: str


class AcpProvider(Provider[AcpAgent]):
    """Pydantic AI v2 provider that treats an ACP agent as the model backend.

    This is the inverse of the normal ``pydantic-acp`` server adapter.  The
    server adapter exposes a ``pydantic_ai.Agent`` through ACP.  ``AcpProvider``
    consumes an existing ACP agent and makes it available to Pydantic AI as a
    provider/model pair, so application code can write ordinary Pydantic AI
    agents while delegating the underlying model turn to ACP.

    The provider owns ACP protocol/session setup, model selection handoff via
    ``set_session_model`` when the remote agent supports it, host/client update
    capture, and prompt rendering.  It deliberately remains a provider rather
    than an alternate agent framework: Pydantic AI still owns the outer agent
    run, result validation, usage accumulation, and history shape.
    """

    def __init__(
        self,
        *,
        agent: AcpAgent,
        cwd: str | Path = ".",
        host_client: AcpClient | None = None,
        name: str = "acp",
        base_url: str = "acp://local",
        protocol_version: int = PROTOCOL_VERSION,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        mcp_servers: Sequence[Any] | None = None,
        prompt_renderer: AcpPromptRenderer | None = None,
    ) -> None:
        self._client = agent
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
        self._initialized = False
        self._session_id: str | None = None
        self._current_model_name: str | None = None
        self._session_lock: asyncio.Lock | None = None
        self._session_lock_loop: asyncio.AbstractEventLoop | None = None

        if hasattr(agent, "on_connect"):
            agent.on_connect(self._host)

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def client(self) -> AcpAgent:
        return self._client

    @property
    def host(self) -> AcpHostBridge:
        """The ACP host bridge connected to the wrapped ACP agent."""
        return self._host

    @staticmethod
    def model_profile(model_name: str) -> ModelProfile | None:
        del model_name
        return ACP_MODEL_PROFILE

    def model(
        self,
        model_name: str = "agent",
        *,
        settings: ModelSettings | None = None,
        profile: ModelProfile | None = None,
    ) -> AcpModel:
        """Build an ``AcpModel`` bound to this provider."""
        return AcpModel(
            model_name=model_name,
            provider=self,
            settings=settings,
            profile=profile,
        )

    async def render_prompt_blocks(
        self,
        messages: Sequence[ModelMessage],
        model_request_parameters: ModelRequestParameters,
    ) -> list[AgentPromptBlock]:
        """Render Pydantic AI model messages into ACP prompt blocks."""
        if self._prompt_renderer is None:
            return _default_render_prompt_blocks(messages, model_request_parameters)
        rendered = self._prompt_renderer(messages, model_request_parameters)
        if inspect.isawaitable(rendered):
            rendered = await rendered
        return list(rendered)

    async def request_prompt(
        self,
        *,
        model_name: str,
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

    async def _ensure_session(self, *, model_name: str) -> str:
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

            if self._current_model_name != model_name:
                set_session_model = getattr(self._client, "set_session_model", None)
                if set_session_model is not None:
                    result = set_session_model(
                        model_id=model_name,
                        session_id=self._session_id,
                    )
                    if inspect.isawaitable(result):
                        await result
                self._current_model_name = model_name

            return self._session_id

    def _get_session_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._session_lock is None or self._session_lock_loop is not loop:
            self._session_lock = asyncio.Lock()
            self._session_lock_loop = loop
        return self._session_lock


class AcpModel(Model[AcpAgent]):
    """Pydantic AI v2 ``Model`` backed by an ACP agent provider."""

    def __init__(
        self,
        model_name: str,
        *,
        provider: AcpProvider,
        settings: ModelSettings | None = None,
        profile: ModelProfile | None = None,
    ) -> None:
        self._model_name = model_name
        self._provider = provider
        super().__init__(settings=settings, profile=profile or ACP_MODEL_PROFILE)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system(self) -> str:
        return self._provider.name

    @property
    def base_url(self) -> str:
        return self._provider.base_url

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
        prompt = await self._provider.render_prompt_blocks(messages, model_request_parameters)
        acp_result = await self._provider.request_prompt(
            model_name=self.model_name,
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
    ):
        del run_context
        response = await self.request(messages, model_settings, model_request_parameters)
        yield _AcpBufferedStreamedResponse(
            model_request_parameters=model_request_parameters,
            response=response,
        )

    @classmethod
    def supported_native_tools(cls) -> frozenset[type[AbstractNativeTool]]:
        return frozenset()

    def _ensure_supported_request(self, params: ModelRequestParameters) -> None:
        if params.function_tools:
            tool_names = ", ".join(tool.name for tool in params.function_tools)
            raise UserError(
                "AcpModel delegates a model turn to an ACP agent and cannot execute "
                f"Pydantic AI function tools directly: {tool_names}. Register tools on "
                "the ACP agent or provide them through an ACP host bridge instead."
            )
        if params.native_tools:
            raise UserError(
                "AcpModel does not expose Pydantic AI native tools directly; use the "
                "ACP agent/provider side for native capabilities."
            )
        if params.output_tools or not params.allow_text_output:
            raise UserError(
                "AcpModel is a text-response provider bridge. Structured/tool-only "
                "output must be implemented by the ACP agent or validated after the run."
            )


@dataclass
class _AcpBufferedStreamedResponse(StreamedResponse):
    response: ModelResponse

    def __post_init__(self) -> None:
        self._usage = self.response.usage
        self.provider_response_id = self.response.provider_response_id
        self.provider_details = self.response.provider_details
        self.finish_reason = self.response.finish_reason

    async def _get_event_iterator(self):
        for part in self.response.parts:
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
        return self.response.model_name or "acp"

    @property
    def provider_name(self) -> str | None:
        return self.response.provider_name

    @property
    def provider_url(self) -> str | None:
        return self.response.provider_url

    @property
    def timestamp(self):
        return self.response.timestamp


def _default_render_prompt_blocks(
    messages: Sequence[ModelMessage],
    model_request_parameters: ModelRequestParameters,
) -> list[AgentPromptBlock]:
    del model_request_parameters
    request = _latest_request(messages)
    if request is None:
        text = _render_messages_as_text(messages)
    else:
        text = _render_request_as_text(request)
    return [text_block(text)] if text else []


def _latest_request(messages: Sequence[ModelMessage]) -> ModelRequest | None:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            return message
    return None


def _render_messages_as_text(messages: Sequence[ModelMessage]) -> str:
    rendered: list[str] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            rendered_text = _render_request_as_text(message)
        else:
            rendered_text = message.text or ""
        if rendered_text:
            rendered.append(rendered_text)
    return "\n\n".join(rendered).strip()


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
    return isinstance(update, AgentMessageChunk) or getattr(update, "session_update", None) == "agent_message_chunk"


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


def _finish_reason_from_acp(stop_reason: str | None):
    if stop_reason in (None, "end_turn", "stop"):
        return "stop"
    if stop_reason in ("max_tokens", "length"):
        return "length"
    if stop_reason == "cancelled":
        return "error"
    return "stop"
