from __future__ import annotations as _annotations

import tomllib
from pathlib import Path
from typing import Any

from acp import PROTOCOL_VERSION
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
from pydantic_ai import Agent
from pydantic_ai.providers import Provider

from pydantic_acp import AcpModel, AcpProvider


class EchoACPAgent:
    def __init__(self) -> None:
        self.client: Any | None = None
        self.initialized_protocols: list[int] = []
        self.session_cwds: list[str] = []
        self.session_models: list[tuple[str, str]] = []
        self.prompts: list[tuple[str, str]] = []

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
        self.initialized_protocols.append(protocol_version)
        return InitializeResponse(
            protocol_version=protocol_version,
            agent_info=Implementation(name="echo-acp-agent", version="test"),
            agent_capabilities=AgentCapabilities(),
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        del mcp_servers, kwargs
        self.session_cwds.append(cwd)
        return NewSessionResponse(session_id=f"session-{len(self.session_cwds)}")

    async def set_session_model(
        self,
        model_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        del kwargs
        self.session_models.append((session_id, model_id))

    async def prompt(
        self,
        prompt: list[Any],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> PromptResponse:
        del message_id, kwargs
        if self.client is None:
            raise AssertionError("ACP agent was not connected to a host client")
        rendered_prompt = "".join(str(getattr(block, "text", "")) for block in prompt)
        self.prompts.append((session_id, rendered_prompt))
        await self.client.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                session_update="agent_message_chunk",
                content=text_block(f"acp echo: {rendered_prompt}"),
            ),
            source="echo-acp-agent",
        )
        return PromptResponse(stop_reason="end_turn")


def test_acp_client_provider_is_plain_pydantic_ai_provider() -> None:
    acp_agent = EchoACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)

    assert isinstance(provider, Provider)
    assert provider.client is acp_agent
    assert provider.name == "acp"
    assert provider.base_url == "acp://local"
    assert model.provider is provider
    assert model.system == "acp"
    assert model.model_name == "zed-agent"
    assert model.base_url == "acp://local"


async def test_pydantic_ai_agent_can_use_acp_as_just_a_provider() -> None:
    acp_agent = EchoACPAgent()
    provider = AcpProvider(agent=acp_agent, cwd="/workspace")
    model = AcpModel(model_name="zed-agent", provider=provider)
    agent = Agent(model)

    result = await agent.run("Summarize the ACP bridge")

    assert "Summarize the ACP bridge" in result.output
    assert acp_agent.initialized_protocols == [PROTOCOL_VERSION]
    assert acp_agent.session_cwds == ["/workspace"]
    assert acp_agent.session_models == [("session-1", "zed-agent")]
    assert len(acp_agent.prompts) == 1
    assert "Summarize the ACP bridge" in acp_agent.prompts[0][1]


def test_pydantic_acp_requires_pydantic_ai_v2() -> None:
    package_pyproject = Path("packages/adapters/pydantic-acp/pyproject.toml")
    data = tomllib.loads(package_pyproject.read_text())
    dependencies = data["project"]["dependencies"]
    pydantic_ai_dependency = next(
        dependency for dependency in dependencies if dependency.startswith("pydantic-ai-slim")
    )

    assert ">=2.0.0" in pydantic_ai_dependency
    assert "==1." not in pydantic_ai_dependency
