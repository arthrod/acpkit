from __future__ import annotations as _annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from acp.schema import SessionMode

from ._version import __version__
from .approvals import ApprovalBridge, NativeApprovalBridge
from .bridges import CapabilityBridge
from .event_projection import EventProjectionMap
from .models import AdapterModel
from .plan import PlanGenerationType
from .projection import DefaultToolClassifier, ProjectionMap, ToolClassifier
from .prompt_capabilities import AdapterPromptCapabilities
from .providers import (
    ConfigOptionsProvider,
    NativePlanPersistenceProvider,
    PlanProvider,
    SessionModelsProvider,
    SessionModesProvider,
)
from .serialization import DefaultOutputSerializer, OutputSerializer
from .session.store import MemorySessionStore, SessionStore
from .slash import SlashCommandProvider

DEFAULT_AGENT_NAME = "langchain-acp"
DEFAULT_AGENT_TITLE = "LangChain ACP"
DEFAULT_AGENT_VERSION = __version__

PlanUpdateMode: TypeAlias = Literal["full", "content"]

__all__ = (
    "DEFAULT_AGENT_NAME",
    "DEFAULT_AGENT_TITLE",
    "DEFAULT_AGENT_VERSION",
    "AdapterConfig",
    "PlanUpdateMode",
)


@dataclass(slots=True, kw_only=True)
class AdapterConfig:
    agent_name: str = DEFAULT_AGENT_NAME
    agent_title: str = DEFAULT_AGENT_TITLE
    agent_version: str = DEFAULT_AGENT_VERSION
    approval_bridge: ApprovalBridge | None = field(default_factory=NativeApprovalBridge)
    available_models: list[AdapterModel] = field(default_factory=list)
    available_modes: list[SessionMode] = field(default_factory=list)
    capability_bridges: Sequence[CapabilityBridge] = field(default_factory=tuple)
    config_options_provider: ConfigOptionsProvider | None = None
    default_model_id: str | None = None
    default_mode_id: str | None = None
    default_plan_generation_type: PlanGenerationType = "structured"
    enable_plan_progress_tools: bool = False
    event_projection_maps: Sequence[EventProjectionMap] = field(default_factory=tuple)
    models_provider: SessionModelsProvider | None = None
    modes_provider: SessionModesProvider | None = None
    native_plan_additional_instructions: str | None = None
    native_plan_persistence_provider: NativePlanPersistenceProvider | None = None
    output_serializer: OutputSerializer = field(default_factory=DefaultOutputSerializer)
    plan_id: str = "acpkit.plan"
    plan_mode_id: str | None = None
    plan_provider: PlanProvider | None = None
    plan_update_mode: PlanUpdateMode = "full"
    projection_maps: Sequence[ProjectionMap] = field(default_factory=tuple)
    prompt_capabilities: AdapterPromptCapabilities = field(
        default_factory=AdapterPromptCapabilities,
    )
    replay_history_on_load: bool = True
    slash_command_provider: SlashCommandProvider | None = None
    session_store: SessionStore = field(default_factory=MemorySessionStore)
    tool_classifier: ToolClassifier = field(default_factory=DefaultToolClassifier)
