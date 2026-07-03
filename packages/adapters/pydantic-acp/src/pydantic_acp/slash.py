from __future__ import annotations as _annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from acp.schema import AvailableCommand, StopReason

from .agent_types import RuntimeAgent
from .session.state import AcpSessionContext, SessionTranscriptUpdate

__all__ = (
    "SlashCommandHandler",
    "SlashCommandProvider",
    "SlashCommandRequest",
    "SlashCommandResult",
    "StaticSlashCommand",
    "StaticSlashCommandProvider",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SlashCommandRequest:
    name: str
    argument: str | None
    raw_prompt: str
    session: AcpSessionContext
    agent: RuntimeAgent


@dataclass(frozen=True, slots=True, kw_only=True)
class SlashCommandResult:
    text: str | None = None
    updates: Sequence[SessionTranscriptUpdate] = ()
    stop_reason: StopReason = "end_turn"
    handled: bool = True
    refresh_session_surface: bool = True


class SlashCommandProvider(Protocol):
    def available_commands(
        self,
        session: AcpSessionContext,
        agent: RuntimeAgent,
    ) -> Sequence[AvailableCommand] | Awaitable[Sequence[AvailableCommand]]: ...

    def handle_command(
        self,
        request: SlashCommandRequest,
    ) -> SlashCommandResult | None | Awaitable[SlashCommandResult | None]: ...


SlashCommandHandler: TypeAlias = Callable[
    [SlashCommandRequest],
    SlashCommandResult | None | Awaitable[SlashCommandResult | None],
]


@dataclass(frozen=True, slots=True, kw_only=True)
class StaticSlashCommand:
    command: AvailableCommand
    handler: SlashCommandHandler


@dataclass(frozen=True, slots=True, kw_only=True)
class StaticSlashCommandProvider:
    commands: Sequence[StaticSlashCommand]

    def available_commands(
        self,
        session: AcpSessionContext,
        agent: RuntimeAgent,
    ) -> Sequence[AvailableCommand]:
        del session, agent
        return [command.command for command in self.commands]

    def handle_command(
        self,
        request: SlashCommandRequest,
    ) -> SlashCommandResult | None | Awaitable[SlashCommandResult | None]:
        for command in self.commands:
            if command.command.name.strip().lower() == request.name:
                return command.handler(request)
        return None
