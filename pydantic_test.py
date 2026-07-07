import asyncio
from datetime import UTC, datetime
from pathlib import Path

from acpremote import connect_acp
from pydantic_ai import Agent
from pydantic_acp import AcpProvider

WORKSPACE = Path(__file__).parent
CHANGELOG = WORKSPACE / "pydantic_test_changelog.md"

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
    remote_agent = connect_acp("ws://127.0.0.1:4566/acp/ws")
    provider = AcpProvider(agent=remote_agent, cwd=str(WORKSPACE))
    model = provider.model("pi")
    agent = Agent(model)

    try:
        for iteration, prompt in enumerate(PROMPTS, start=1):
            result = await agent.run(prompt)
            print(f"[{iteration}] {result.output}")
            append_changelog(iteration, prompt, result.output)
    finally:
        await remote_agent.close()


if __name__ == "__main__":
    asyncio.run(main())
