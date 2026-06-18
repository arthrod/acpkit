from __future__ import annotations as _annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar

from acp import PROTOCOL_VERSION
from acp.helpers import text_block
from acp.interfaces import Agent as AcpAgent
from acp.schema import (
    AgentPlanUpdate,
    AgentThoughtChunk,
    AvailableCommandsUpdate,
    ConfigOptionUpdate,
    CurrentModeUpdate,
    HttpMcpServer,
    McpServerStdio,
    PlanEntry,
    SessionInfoUpdate,
    SseMcpServer,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UsageUpdate,
)
from pydantic_ai import Agent as PydanticAgent

from ..agent_source import AgentFactory, AgentSource
from ..config import AdapterConfig
from ..runtime.server import create_acp_agent
from .fakes import RecordingACPClient, UpdateRecord, agent_message_texts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..hook_projection import HookProjectionMap
    from ..projection import ProjectionMap

AgentDepsT = TypeVar("AgentDepsT", contravariant=True)
OutputDataT = TypeVar("OutputDataT", covariant=True)
UpdateT = TypeVar("UpdateT")
McpServerDefinition = HttpMcpServer | SseMcpServer | McpServerStdio

__all__ = ("BlackBoxHarness",)


@dataclass(slots=True, kw_only=True)
class BlackBoxHarness:
    adapter: AcpAgent
    client: RecordingACPClient = field(default_factory=RecordingACPClient)
    last_session_id: str | None = None

    def __post_init__(self) -> None:
        self.adapter.on_connect(self.client)

    @classmethod
    def create(
        cls,
        *,
        agent: PydanticAgent[AgentDepsT, OutputDataT] | None = None,
        agent_factory: AgentFactory[AgentDepsT, OutputDataT] | None = None,
        agent_source: AgentSource[AgentDepsT, OutputDataT] | None = None,
        config: AdapterConfig | None = None,
        projection_maps: Sequence[ProjectionMap | HookProjectionMap] | None = None,
        client: RecordingACPClient | None = None,
    ) -> BlackBoxHarness:
        adapter = create_acp_agent(
            agent=agent,
            agent_factory=agent_factory,
            agent_source=agent_source,
            config=config,
            projection_maps=projection_maps,
        )
        return cls(adapter=adapter, client=client or RecordingACPClient())

    async def initialize(self, protocol_version: int = PROTOCOL_VERSION):
        return await self.adapter.initialize(protocol_version=protocol_version)

    async def new_session(
        self,
        *,
        cwd: str,
        mcp_servers: Sequence[McpServerDefinition] | None = None,
    ):
        response = await self.adapter.new_session(
            cwd=cwd,
            mcp_servers=list(mcp_servers) if mcp_servers is not None else [],
        )
        self.last_session_id = response.session_id
        return response

    async def load_session(
        self,
        *,
        cwd: str,
        session_id: str | None = None,
        mcp_servers: Sequence[McpServerDefinition] | None = None,
    ):
        resolved_session_id = self.require_session_id(session_id)
        response = await self.adapter.load_session(
            cwd=cwd,
            session_id=resolved_session_id,
            mcp_servers=list(mcp_servers) if mcp_servers is not None else [],
        )
        if response is not None:
            self.last_session_id = resolved_session_id
        return response

    async def prompt_text(
        self,
        text: str,
        *,
        session_id: str | None = None,
        message_id: str | None = None,
    ):
        return await self.adapter.prompt(
            prompt=[text_block(text)],
            session_id=self.require_session_id(session_id),
            message_id=message_id,
        )

    async def set_mode(self, mode_id: str, *, session_id: str | None = None):
        return await self.adapter.set_session_mode(
            mode_id=mode_id,
            session_id=self.require_session_id(session_id),
        )

    async def set_model(self, model_id: str, *, session_id: str | None = None):
        return await self.adapter.set_session_model(
            model_id=model_id,
            session_id=self.require_session_id(session_id),
        )

    async def set_config_option(
        self,
        config_id: str,
        value: str | bool,
        *,
        session_id: str | None = None,
    ):
        return await self.adapter.set_config_option(
            config_id=config_id,
            session_id=self.require_session_id(session_id),
            value=value,
        )

    async def list_sessions(self, *, cursor: str | None = None, cwd: str | None = None):
        return await self.adapter.list_sessions(cursor=cursor, cwd=cwd)

    async def fork_session(
        self,
        *,
        cwd: str,
        session_id: str | None = None,
        mcp_servers: Sequence[McpServerDefinition] | None = None,
    ):
        response = await self.adapter.fork_session(
            cwd=cwd,
            session_id=self.require_session_id(session_id),
            mcp_servers=list(mcp_servers) if mcp_servers is not None else [],
        )
        self.last_session_id = response.session_id
        return response

    async def resume_session(
        self,
        *,
        cwd: str,
        session_id: str | None = None,
        mcp_servers: Sequence[McpServerDefinition] | None = None,
    ):
        resolved_session_id = self.require_session_id(session_id)
        response = await self.adapter.resume_session(
            cwd=cwd,
            session_id=resolved_session_id,
            mcp_servers=list(mcp_servers) if mcp_servers is not None else [],
        )
        self.last_session_id = resolved_session_id
        return response

    async def close_session(self, *, session_id: str | None = None):
        return await self.adapter.close_session(session_id=self.require_session_id(session_id))

    def require_session_id(self, session_id: str | None = None) -> str:
        resolved_session_id = self.last_session_id if session_id is None else session_id
        if resolved_session_id is None:
            raise ValueError("No active session id is available.")
        return resolved_session_id

    def queue_permission_selected(self, option_id: str) -> None:
        self.client.queue_permission_selected(option_id)

    def queue_permission_cancelled(self) -> None:
        self.client.queue_permission_cancelled()

    def clear_updates(self) -> None:
        self.client.updates.clear()

    def updates(self, *, session_id: str | None = None) -> list[UpdateRecord]:
        if session_id is None:
            return list(self.client.updates)
        return [record for record in self.client.updates if record.session_id == session_id]

    def updates_of_type(
        self,
        update_type: type[UpdateT],
        *,
        session_id: str | None = None,
    ) -> list[UpdateT]:
        records = self.updates(session_id=session_id)
        return [record.update for record in records if isinstance(record.update, update_type)]

    def agent_messages(self, *, session_id: str | None = None) -> list[str]:
        if session_id is None:
            return agent_message_texts(self.client)
        scoped_client = RecordingACPClient(updates=self.updates(session_id=session_id))
        return agent_message_texts(scoped_client)

    def available_command_names(self, *, session_id: str | None = None) -> list[str]:
        command_updates = self.updates_of_type(AvailableCommandsUpdate, session_id=session_id)
        if not command_updates:
            return []
        return [command.name for command in command_updates[-1].available_commands]

    def current_mode_updates(self, *, session_id: str | None = None) -> list[CurrentModeUpdate]:
        return self.updates_of_type(CurrentModeUpdate, session_id=session_id)

    def current_mode_id(self, *, session_id: str | None = None) -> str | None:
        mode_updates = self.current_mode_updates(session_id=session_id)
        if not mode_updates:
            return None
        return mode_updates[-1].current_mode_id

    def config_option_updates(
        self,
        *,
        session_id: str | None = None,
    ) -> list[ConfigOptionUpdate]:
        return self.updates_of_type(ConfigOptionUpdate, session_id=session_id)

    def plan_updates(self, *, session_id: str | None = None) -> list[AgentPlanUpdate]:
        return self.updates_of_type(AgentPlanUpdate, session_id=session_id)

    def last_plan_entries(self, *, session_id: str | None = None) -> list[PlanEntry]:
        plan_updates = self.plan_updates(session_id=session_id)
        if not plan_updates:
            return []
        return list(plan_updates[-1].entries)

    def thought_chunks(self, *, session_id: str | None = None) -> list[AgentThoughtChunk]:
        return self.updates_of_type(AgentThoughtChunk, session_id=session_id)

    def session_info_updates(self, *, session_id: str | None = None) -> list[SessionInfoUpdate]:
        return self.updates_of_type(SessionInfoUpdate, session_id=session_id)

    def usage_updates(self, *, session_id: str | None = None) -> list[UsageUpdate]:
        return self.updates_of_type(UsageUpdate, session_id=session_id)

    def permission_requests(self, *, session_id: str | None = None) -> list[ToolCallUpdate]:
        if session_id is None:
            return [request[2] for request in self.client.permission_option_ids]
        return [
            request[2] for request in self.client.permission_option_ids if request[0] == session_id
        ]

    def permission_request_option_ids(self, *, session_id: str | None = None) -> list[list[str]]:
        if session_id is None:
            return [request[1] for request in self.client.permission_option_ids]
        return [
            request[1] for request in self.client.permission_option_ids if request[0] == session_id
        ]

    def permission_request_option_names(self, *, session_id: str | None = None) -> list[list[str]]:
        if session_id is None:
            return [request[1] for request in self.client.permission_option_names]
        return [
            request[1]
            for request in self.client.permission_option_names
            if request[0] == session_id
        ]

    def last_permission_request(self, *, session_id: str | None = None) -> ToolCallUpdate | None:
        requests = self.permission_requests(session_id=session_id)
        return requests[-1] if requests else None

    def tool_updates(
        self,
        *,
        session_id: str | None = None,
    ) -> list[ToolCallStart | ToolCallProgress]:
        return [
            record.update
            for record in self.updates(session_id=session_id)
            if isinstance(record.update, ToolCallStart | ToolCallProgress)
        ]
