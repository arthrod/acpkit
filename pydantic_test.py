import asyncio
from datetime import UTC, datetime
from pathlib import Path

import acp.utils as _acp_utils
from acpremote import CommandOptions, connect_acp, serve_stdio_command
from pydantic_ai import Agent
from pydantic_acp import AcpProvider

# MODEL: any id pi exposes works here. Alternatives (from pi's new_session response):
#   "MiniMax-M2.7" / "MiniMax-M2.7-highspeed" / "MiniMax-M3"        (minimax-coding-plan, needs MINIMAX_API_KEY)
#   "gemini-2.5-pro" / "gemini-3-pro-preview" / "gemini-2.5-flash"  (google-gemini-cli, needs `pi login` gemini)
#   "claude-sonnet-4-5" / "gemini-3-flash"                          (google-antigravity, needs `pi login` antigravity)
#   "gpt-5.2-codex" / "gpt-5.1"                                     (openai-codex, needs `pi login` codex — token currently expired)
MODEL_ID = "minimax/MiniMax-M3"
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
    # Start pi-acp as a stdio command and expose it over WebSocket
    print("Starting pi-acp server...")
    command_opts = CommandOptions(command=("pi-acp",), cwd=str(WORKSPACE))
    server = await serve_stdio_command(
        command_options=command_opts,
        host="127.0.0.1",
        port=0,  # Let OS assign a free port
    )
    sockets = list(server.sockets)
    port = sockets[0].getsockname()[1]
    ws_url = f"ws://127.0.0.1:{port}/acp/ws"
    print(f"pi-acp server started on {ws_url}")

    try:
        print("Connecting to ACP server...")
        remote_agent = connect_acp(ws_url)
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
            result = await asyncio.wait_for(agent.run("Say hello"), timeout=100)
            print(f"Result: {result.output}")
        except TimeoutError:
            print("ERROR: agent.run timed out after 100 seconds")
        finally:
            print("Closing connection...")
            await remote_agent.close()
    finally:
        print("Closing server...")
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
