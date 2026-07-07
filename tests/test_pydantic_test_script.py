from __future__ import annotations as _annotations

import importlib.util
from pathlib import Path

import pytest


def _load_pydantic_test_script():
    module_path = Path(__file__).resolve().parents[1] / "pydantic_test.py"
    spec = importlib.util.spec_from_file_location("pydantic_test_script", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_pydantic_test_script()


@pytest.fixture
def changelog_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "pydantic_test_changelog.md"
    monkeypatch.setattr(script, "CHANGELOG", path)
    return path


def test_append_changelog_creates_file_with_header_on_first_write(changelog_path: Path) -> None:
    assert not changelog_path.exists()

    script.append_changelog(1, "What is the capital of France?", "Paris")

    content = changelog_path.read_text(encoding="utf-8")
    assert content.startswith("# pydantic_test changelog\n\n")
    assert "run 1" in content
    assert "**Prompt:** What is the capital of France?" in content
    assert "**Response:** Paris" in content


def test_append_changelog_does_not_repeat_header_on_subsequent_writes(changelog_path: Path) -> None:
    script.append_changelog(1, "first prompt", "first response")
    script.append_changelog(2, "second prompt", "second response")

    content = changelog_path.read_text(encoding="utf-8")

    assert content.count("# pydantic_test changelog") == 1
    assert "run 1" in content
    assert "run 2" in content
    assert "**Prompt:** first prompt" in content
    assert "**Prompt:** second prompt" in content
    assert content.index("run 1") < content.index("run 2")


def test_append_changelog_preserves_existing_content_across_calls(changelog_path: Path) -> None:
    changelog_path.write_text("# pydantic_test changelog\n\nexisting entry\n\n", encoding="utf-8")

    script.append_changelog(3, "third prompt", "third response")

    content = changelog_path.read_text(encoding="utf-8")
    assert content.count("# pydantic_test changelog") == 1
    assert "existing entry" in content
    assert "run 3" in content


def test_prompts_list_and_workspace_paths_are_defined() -> None:
    assert len(script.PROMPTS) == 3
    assert all(isinstance(prompt, str) and prompt for prompt in script.PROMPTS)
    assert script.CHANGELOG.name == "pydantic_test_changelog.md"
    assert script.CHANGELOG.parent == script.WORKSPACE