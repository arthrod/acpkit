from __future__ import annotations as _annotations

from dataclasses import dataclass, field

from acp.schema import (
    ContentToolCallContent,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallStatus,
)

__all__ = ("HookEvent", "HookProjectionMap")


@dataclass(frozen=True, slots=True, kw_only=True)
class HookEvent:
    event_id: str
    hook_name: str
    summary: str
    detail: str | None = None
    status: ToolCallStatus | None = None
    hidden: bool = False


@dataclass(slots=True, kw_only=True)
class HookProjectionMap:
    title_prefix: str = "Hook"
    hidden_event_ids: set[str] = field(default_factory=set)

    def build_start_update(
        self,
        *,
        tool_call_id: str,
        event: HookEvent,
    ) -> ToolCallStart | None:
        if event.hidden:
            self.hidden_event_ids.add(event.event_id)
            return None
        return ToolCallStart(
            session_update="tool_call",
            tool_call_id=tool_call_id,
            title=f"{self.title_prefix}: {event.hook_name}",
            kind="execute",
            status="in_progress",
            raw_input={"event_id": event.event_id, "summary": event.summary},
            content=[
                ContentToolCallContent(
                    type="content",
                    content=TextContentBlock(type="text", text=event.summary),
                ),
            ],
        )

    def build_progress_update(
        self,
        *,
        tool_call_id: str,
        event: HookEvent,
    ) -> ToolCallProgress | None:
        if event.hidden:
            self.hidden_event_ids.add(event.event_id)
            return None
        detail = event.detail or event.summary
        return ToolCallProgress(
            session_update="tool_call_update",
            tool_call_id=tool_call_id,
            title=f"{self.title_prefix}: {event.hook_name}",
            kind="execute",
            status=event.status or "completed",
            raw_output=detail,
            content=[
                ContentToolCallContent(
                    type="content",
                    content=TextContentBlock(type="text", text=detail),
                ),
            ],
        )
