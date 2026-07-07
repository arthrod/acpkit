import asyncio
import json
from pathlib import Path

import acp.utils as _acp_utils
from acpremote import connect_acp
from pydantic_ai import Agent
from pydantic_acp import AcpProvider
from pydantic_acp.client import AcpHostBridge

MODEL_ID = "MiniMax-M2.7"
WORKSPACE = Path("/Users/arthrod/temp/T/acpkit")

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


async def main():
    remote_agent = connect_acp("ws://127.0.0.1:4566/acp/ws")
    provider = AcpProvider(agent=remote_agent, cwd=str(WORKSPACE))
    model = provider.model(MODEL_ID)
    agent = Agent(model)

    # monkey-patch the host bridge to log every update
    orig_session_update = AcpHostBridge.session_update

    async def logged_session_update(self, session_id, update, **kwargs):
        print("UPDATE:", type(update).__name__, json.dumps(update, default=str)[:500])
        return await orig_session_update(self, session_id, update, **kwargs)

    AcpHostBridge.session_update = logged_session_update

    orig_request_prompt = AcpProvider.request_prompt

    async def logged_request_prompt(self, *, model_name, prompt):
        session_id = await self._ensure_session(model_name=model_name)
        start_index = self._host.snapshot_index()
        prompt_response = await self._client.prompt(
            prompt=list(prompt),
            session_id=session_id,
            message_id="probe-msg-id",
        )
        print("RAW PROMPT_RESPONSE TYPE:", type(prompt_response).__name__)
        print("RAW PROMPT_RESPONSE:", json.dumps(prompt_response, default=str)[:2000])
        text = self._host.agent_message_text_since(start_index, session_id=session_id)
        print("HOST TEXT:", repr(text))
        usage = getattr(self, "_usage_from_acp", None)
        from pydantic_acp.client import _usage_from_acp, _finish_reason_from_acp

        usage = _usage_from_acp(getattr(prompt_response, "usage", None))
        if not usage.has_values():
            usage = self._host.usage_update_since(start_index, session_id=session_id)
        stop_reason = getattr(prompt_response, "stop_reason", None) or getattr(
            prompt_response,
            "stopReason",
            None,
        )
        from pydantic_acp.client import _AcpPromptResult

        return _AcpPromptResult(
            text=text,
            usage=usage,
            stop_reason=stop_reason,
            session_id=session_id,
        )

    AcpProvider.request_prompt = logged_request_prompt

    try:
        result = await agent.run("What is the capital of France?")
        print("RESULT:", result.output)
    finally:
        await remote_agent.close()


if __name__ == "__main__":
    asyncio.run(main())
