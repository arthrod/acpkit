from __future__ import annotations as _annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from acp.schema import ToolCallStatus, ToolCallUpdate

from .projection import ProjectionMap, ToolClassifier, extract_tool_call_locations
from .session.state import AcpSessionContext

__all__ = (
    "DefaultPermissionToolCallBuilder",
    "PermissionRequestContext",
    "PermissionToolCallBuilder",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionRequestContext:
    session: AcpSessionContext
    tool_call_id: str
    tool_name: str
    raw_input: dict[str, Any]
    cwd: Path
    classifier: ToolClassifier
    projection_map: ProjectionMap | None = None


class PermissionToolCallBuilder(Protocol):
    def build_tool_call_update(
        self,
        context: PermissionRequestContext,
    ) -> ToolCallUpdate: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class DefaultPermissionToolCallBuilder:
    status: ToolCallStatus = "pending"

    def build_tool_call_update(
        self,
        context: PermissionRequestContext,
    ) -> ToolCallUpdate:
        projection = None
        if context.projection_map is not None:
            projection = context.projection_map.project_start(
                context.tool_name,
                cwd=context.cwd,
                raw_input=context.raw_input,
            )
        return ToolCallUpdate(
            tool_call_id=context.tool_call_id,
            title=(
                projection.title
                if projection is not None and projection.title is not None
                else context.tool_name
            ),
            kind=context.classifier.classify(context.tool_name, context.raw_input),
            content=projection.content if projection is not None else None,
            locations=(
                projection.locations
                if projection is not None and projection.locations is not None
                else extract_tool_call_locations(context.raw_input)
            ),
            raw_input=context.raw_input,
            status=self.status,
        )
