import asyncio
from datetime import UTC, datetime
from pathlib import Path

import acp.utils as _acp_utils
from acpremote import connect_acp
from pydantic_ai import Agent
from pydantic_acp import AcpProvider

# MODEL: any id pi exposes works here. Alternatives (from pi's new_session response):
#   "MiniMax-M2.7" / "MiniMax-M2.7-highspeed" / "MiniMax-M3"        (minimax-coding-plan, needs MINIMAX_API_KEY)
#   "gemini-2.5-pro" / "gemini-3-pro-preview" / "gemini-2.5-flash"  (google-gemini-cli, needs `pi login` gemini)
#   "claude-sonnet-4-5" / "gemini-3-flash"                          (google-antigravity, needs `pi login` antigravity)
#   "gpt-5.2-codex" / "gpt-5.1"                                     (openai-codex, needs `pi login` codex — token currently expired)
MODEL_ID = "MiniMax-M3"
PROVIDER_ID = "minimax"
WORKSPACE = Path(__file__).parent
CHANGELOG = WORKSPACE / "pydantic_test_changelog.md"

# pi returns `models`/`modes` as plain lists; acp==0.9.0 expects state objects.
# Coerce the new_session payload into the expected shape before validation.
_orig_validate_model = _acp_utils.validate_model


def _pi_compat_validate(payload, model_type):
    if getattr(model_type, "__name__", "") == "NewSessionResponse" and isinstance(payload, dict):
        models = payload.get("models")
        if isinstance(models, list):
            payload["models"] = {
                "availableModels": [
                    {"modelId": m.get("id", ""), "name": m.get("name", ""), "description": m.get("provider")}
                    for m in models
                ],
                "currentModelId": MODEL_ID,
            }
        modes = payload.get("modes")
        if isinstance(modes, list):
            available = [
                {"id": m.get("slug", m.get("id", "")), "name": m.get("name", ""), "description": m.get("description")}
                for m in modes
            ]
            payload["modes"] = {
                "availableModes": available,
                "currentModeId": available[0]["id"] if available else "",
            }
    return _orig_validate_model(payload, model_type)


_acp_utils.validate_model = _pi_compat_validate

PROMPTS = [
    "What is the capital of France?",
    "In one sentence, what does the ACP protocol do?",
    "In one sentence, why would someone bridge pydantic-ai to ACP?",
]


def append_changelog(iteration: int, prompt: str, response: str) -> None:
    header = "" if CHANGELOG.exists() else "# pydantic_test changelog\n\n"
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    entry = f"## {stamp} — run {iteration}\n\n**Prompt:** {prompt}\n\n**Response:** {response}\n\n"
    with CHANGELOG.open("a", encoding="utf-8") as handle:
        handle.write(header + entry)


async def main() -> None:
    print("Connecting to ACP server...")
    remote_agent = connect_acp("ws://127.0.0.1:4566/acp/ws")
    print("Connected, creating provider...")
    provider = AcpProvider(agent=remote_agent, cwd=str(WORKSPACE))
    print("Getting model...")
    model = provider.model(MODEL_ID)
    print("Creating agent...")
    agent = Agent(model)
    print("Agent created successfully")

    try:
        print("Testing single prompt...")
        print("Calling agent.run...")
        result = await asyncio.wait_for(agent.run("Say hello"), timeout=10)
        print(f"Result: {result.output}")
    except TimeoutError:
        print("ERROR: agent.run timed out after 10 seconds")
    finally:
        print("Closing connection...")
        await remote_agent.close()


if __name__ == "__main__":
    asyncio.run(main())
