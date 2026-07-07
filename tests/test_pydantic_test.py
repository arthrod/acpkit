from __future__ import annotations as _annotations

from pathlib import Path
from typing import Any

import pydantic_test
import pytest
from acp.helpers import text_block
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    ClientCapabilities,
    Implementation,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
)


class FakeRemoteAcpAgent:
    """A minimal ACP agent double standing in for a real ``acpremote`` connection."""

    def __init__(self) -> None:
        self.client: Any | None = None
        self.closed = False
        self.prompts: list[str] = []

    def on_connect(self, conn: Any) -> None:
        self.client = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        del client_capabilities, client_info, kwargs
        return InitializeResponse(
            protocol_version=protocol_version,
            agent_info=Implementation(name="fake-remote-agent", version="test"),
            agent_capabilities=AgentCapabilities(),
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        del cwd, mcp_servers, kwargs
        return NewSessionResponse(session_id="session-1")

    async def prompt(
        self,
        prompt: list[Any],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> PromptResponse:
        del message_id, kwargs
        if self.client is None:
            raise AssertionError("fake remote agent was not connected to a host client")
        rendered_prompt = "".join(str(getattr(block, "text", "")) for block in prompt)
        self.prompts.append(rendered_prompt)
        await self.client.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                session_update="agent_message_chunk",
                content=text_block(f"echo: {rendered_prompt}"),
            ),
        )
        return PromptResponse(stop_reason="end_turn")

    async def close(self) -> None:
        self.closed = True


def test_append_changelog_writes_header_only_on_first_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    changelog = tmp_path / "changelog.md"
    monkeypatch.setattr(pydantic_test, "CHANGELOG", changelog)

    pydantic_test.append_changelog(1, "What is 2+2?", "4")

    content = changelog.read_text(encoding="utf-8")
    assert content.startswith("# pydantic_test changelog\n\n")
    assert "run 1" in content
    assert "**Prompt:** What is 2+2?" in content
    assert "**Response:** 4" in content


def test_append_changelog_does_not_duplicate_header_on_later_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changelog = tmp_path / "changelog.md"
    monkeypatch.setattr(pydantic_test, "CHANGELOG", changelog)

    pydantic_test.append_changelog(1, "first prompt", "first response")
    pydantic_test.append_changelog(2, "second prompt", "second response")

    content = changelog.read_text(encoding="utf-8")
    assert content.count("# pydantic_test changelog") == 1
    assert "run 1" in content
    assert "run 2" in content
    assert "first prompt" in content
    assert "second prompt" in content


def test_prompts_constant_has_the_expected_shape() -> None:
    assert len(pydantic_test.PROMPTS) == 3
    assert all(isinstance(prompt, str) and prompt for prompt in pydantic_test.PROMPTS)


async def test_main_runs_every_prompt_through_the_acp_provider_and_logs_each_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_agent = FakeRemoteAcpAgent()
    changelog = tmp_path / "changelog.md"
    monkeypatch.setattr(pydantic_test, "CHANGELOG", changelog)
    monkeypatch.setattr(pydantic_test, "connect_acp", lambda *args, **kwargs: fake_agent)

    await pydantic_test.main()

    assert fake_agent.closed is True
    assert fake_agent.prompts == pydantic_test.PROMPTS

    captured = capsys.readouterr()
    for index, prompt in enumerate(pydantic_test.PROMPTS, start=1):
        assert f"[{index}] echo: {prompt}" in captured.out

    changelog_content = changelog.read_text(encoding="utf-8")
    assert changelog_content.count("# pydantic_test changelog") == 1
    for index, prompt in enumerate(pydantic_test.PROMPTS, start=1):
        assert f"run {index}" in changelog_content
        assert prompt in changelog_content


async def test_main_closes_the_remote_agent_even_if_a_prompt_run_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRemoteAcpAgent(FakeRemoteAcpAgent):
        async def prompt(
            self,
            prompt: list[Any],
            session_id: str,
            message_id: str | None = None,
            **kwargs: Any,
        ) -> PromptResponse:
            raise RuntimeError("boom")

    fake_agent = FailingRemoteAcpAgent()
    monkeypatch.setattr(pydantic_test, "CHANGELOG", tmp_path / "changelog.md")
    monkeypatch.setattr(pydantic_test, "connect_acp", lambda *args, **kwargs: fake_agent)

    with pytest.raises(RuntimeError, match="boom"):
        await pydantic_test.main()

    assert fake_agent.closed is True