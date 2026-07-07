from __future__ import annotations as _annotations

import importlib.util
from pathlib import Path

import pytest


def _load_probe_prompt_script():
    module_path = Path(__file__).resolve().parents[1] / "probe_prompt.py"
    spec = importlib.util.spec_from_file_location("probe_prompt_script", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_probe_prompt_script()


def test_module_defines_expected_model_id_and_workspace() -> None:
    assert script.MODEL_ID == "MiniMax-M2.7"
    assert isinstance(script.WORKSPACE, Path)


def test_module_patches_acp_utils_validate_model_with_pi_compat_validate() -> None:
    import acp.utils as acp_utils

    assert acp_utils.validate_model is script._pi_compat_validate


# --- `_pi_compat_validate` (pi -> acp==0.9.0 NewSessionResponse payload shim) --------


class _FakeNewSessionResponseType:
    __name__ = "NewSessionResponse"


class _OtherModelType:
    __name__ = "SomeOtherResponse"


@pytest.fixture
def recording_orig_validate_model(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace `script._orig_validate_model` with a stub that records its call.

    The stub returns the (possibly transformed) payload unchanged, so tests can
    assert on exactly what `_pi_compat_validate` forwarded downstream without
    depending on real `acp` schema validation.
    """
    captured: dict[str, object] = {}

    def fake_orig(payload: object, model_type: object) -> object:
        captured["payload"] = payload
        captured["model_type"] = model_type
        return payload

    monkeypatch.setattr(script, "_orig_validate_model", fake_orig)
    return captured


def test_pi_compat_validate_converts_list_models_into_available_models_state(
    recording_orig_validate_model: dict[str, object],
) -> None:
    payload = {
        "models": [
            {"id": "model-a", "name": "Model A", "provider": "provider-a"},
            {"id": "model-b", "name": "Model B", "provider": "provider-b"},
        ]
    }

    result = script._pi_compat_validate(payload, _FakeNewSessionResponseType())

    assert result["models"] == {
        "availableModels": [
            {"modelId": "model-a", "name": "Model A", "description": "provider-a"},
            {"modelId": "model-b", "name": "Model B", "description": "provider-b"},
        ],
        "currentModelId": script.MODEL_ID,
    }
    assert recording_orig_validate_model["payload"] is payload


def test_pi_compat_validate_converts_list_modes_using_slug_as_id(
    recording_orig_validate_model: dict[str, object],
) -> None:
    payload = {
        "modes": [
            {"slug": "chat", "name": "Chat", "description": "Conversational mode"},
            {"id": "review-id", "name": "Review", "description": "Review mode"},
        ]
    }

    result = script._pi_compat_validate(payload, _FakeNewSessionResponseType())

    assert result["modes"] == {
        "availableModes": [
            {"id": "chat", "name": "Chat", "description": "Conversational mode"},
            {"id": "review-id", "name": "Review", "description": "Review mode"},
        ],
        "currentModeId": "chat",
    }


def test_pi_compat_validate_sets_empty_current_mode_id_when_modes_list_is_empty(
    recording_orig_validate_model: dict[str, object],
) -> None:
    result = script._pi_compat_validate({"modes": []}, _FakeNewSessionResponseType())

    assert result["modes"] == {"availableModes": [], "currentModeId": ""}


def test_pi_compat_validate_ignores_payloads_for_other_model_types(
    recording_orig_validate_model: dict[str, object],
) -> None:
    payload = {"models": [{"id": "model-a", "name": "Model A"}]}

    result = script._pi_compat_validate(payload, _OtherModelType())

    # The payload must be forwarded untouched: no list -> state-object conversion.
    assert result["models"] == [{"id": "model-a", "name": "Model A"}]


def test_pi_compat_validate_ignores_non_dict_payloads(
    recording_orig_validate_model: dict[str, object],
) -> None:
    already_valid_object = object()

    result = script._pi_compat_validate(already_valid_object, _FakeNewSessionResponseType())

    assert result is already_valid_object


def test_pi_compat_validate_leaves_payload_untouched_when_models_and_modes_are_absent(
    recording_orig_validate_model: dict[str, object],
) -> None:
    payload = {"session_id": "session-1"}

    result = script._pi_compat_validate(payload, _FakeNewSessionResponseType())

    assert result == {"session_id": "session-1"}


def test_pi_compat_validate_leaves_already_structured_models_and_modes_alone(
    recording_orig_validate_model: dict[str, object],
) -> None:
    payload = {
        "models": {"availableModels": [], "currentModelId": "already-structured"},
        "modes": {"availableModes": [], "currentModeId": "already-structured"},
    }

    result = script._pi_compat_validate(payload, _FakeNewSessionResponseType())

    assert result["models"] == {"availableModels": [], "currentModelId": "already-structured"}
    assert result["modes"] == {"availableModes": [], "currentModeId": "already-structured"}


def test_pi_compat_validate_forwards_return_value_from_original_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    monkeypatch.setattr(script, "_orig_validate_model", lambda payload, model_type: sentinel)

    result = script._pi_compat_validate({"models": []}, _FakeNewSessionResponseType())

    assert result is sentinel