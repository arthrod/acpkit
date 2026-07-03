from __future__ import annotations as _annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from ..hook_projection import HookEvent, HookProjectionMap
from ..session.state import AcpSessionContext, JsonValue
from .base import BufferedCapabilityBridge

__all__ = ("EventEmissionMode", "ExternalHookEventBridge")

EventEmissionMode: TypeAlias = Literal["paired", "start_only"]


@dataclass(slots=True, kw_only=True)
class ExternalHookEventBridge(BufferedCapabilityBridge):
    metadata_key: str | None = "external_hooks"
    projection_map: HookProjectionMap = field(default_factory=HookProjectionMap)
    emission_mode: EventEmissionMode = "paired"

    def record_event(
        self,
        session: AcpSessionContext,
        event: HookEvent,
        *,
        emission_mode: EventEmissionMode | None = None,
    ) -> None:
        mode = self.emission_mode if emission_mode is None else emission_mode
        tool_call_id = self._next_event_id(session)
        start_update = self.projection_map.build_start_update(
            tool_call_id=tool_call_id,
            event=event,
        )
        if start_update is None:
            return
        if mode == "start_only":
            if event.status is not None:
                start_update.status = event.status
            self._append_updates(session, [start_update])
            return
        progress_update = self.projection_map.build_progress_update(
            tool_call_id=tool_call_id,
            event=event,
        )
        if progress_update is None:
            self._append_updates(session, [start_update])
            return
        self._append_updates(session, [start_update, progress_update])

    def get_session_metadata(self, session: AcpSessionContext) -> dict[str, JsonValue]:
        hidden_event_ids: list[JsonValue] = []
        hidden_event_ids.extend(sorted(self.projection_map.hidden_event_ids))
        return {
            "emission_mode": self.emission_mode,
            "pending_event_count": len(self._pending_updates.get(session.session_id, ())),
            "hidden_event_ids": hidden_event_ids,
            "projection_title_prefix": self.projection_map.title_prefix,
        }
