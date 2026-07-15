from __future__ import annotations as _annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

from acp.exceptions import RequestError
from acp.schema import (
    AvailableCommand,
    PlanEntry,
    SessionConfigOptionBoolean,
    SessionConfigOptionSelect,
    SessionConfigSelectOption,
    SessionModeState,
)

from ..models import AdapterModel
from ..providers import ModelSelectionState, ModeState

ConfigOption: TypeAlias = SessionConfigOptionSelect | SessionConfigOptionBoolean

__all__ = (
    "ConfigOption",
    "SessionSurface",
    "build_mode_config_option",
    "build_mode_state_from_selection",
    "build_model_config_option",
    "find_model_option",
)


@dataclass(slots=True, kw_only=True)
class SessionSurface:
    config_options: list[ConfigOption] | None
    mode_state: SessionModeState | None
    plan_entries: list[PlanEntry] | None
    available_commands: list[AvailableCommand] | None = None


def build_model_config_option(
    model_selection_state: ModelSelectionState,
) -> SessionConfigOptionSelect:
    current_model_id = model_selection_state.current_model_id
    if current_model_id is None:
        raise RequestError.internal_error({"reason": "missing_current_model_id"})
    return SessionConfigOptionSelect(
        id="model",
        name=model_selection_state.config_option_name,
        category="model",
        description=model_selection_state.config_option_description,
        type="select",
        current_value=current_model_id,
        options=[
            SessionConfigSelectOption(
                value=model.model_id,
                name=model.name,
                description=model.description,
            )
            for model in model_selection_state.available_models
        ],
    )


def build_mode_config_option(mode_state: ModeState) -> SessionConfigOptionSelect:
    current_mode_id = mode_state.current_mode_id
    if current_mode_id is None:
        raise RequestError.internal_error({"reason": "missing_current_mode_id"})
    return SessionConfigOptionSelect(
        id="mode",
        name="Mode",
        category="mode",
        description="Session-local mode selection.",
        type="select",
        current_value=current_mode_id,
        options=[
            SessionConfigSelectOption(
                value=mode.id,
                name=mode.name,
                description=mode.description,
            )
            for mode in mode_state.modes
        ],
    )


def build_mode_state_from_selection(
    mode_state: ModeState | None,
) -> SessionModeState | None:
    if mode_state is None or mode_state.current_mode_id is None or not mode_state.modes:
        return None
    return SessionModeState(
        available_modes=list(mode_state.modes),
        current_mode_id=mode_state.current_mode_id,
    )


def find_model_option(
    model_id: str,
    *,
    available_models: Sequence[AdapterModel],
) -> AdapterModel | None:
    for model in available_models:
        if model.model_id == model_id:
            return model
    return None
