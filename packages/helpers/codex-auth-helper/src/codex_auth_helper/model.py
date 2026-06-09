from __future__ import annotations as _annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from pydantic_ai.messages import ModelRequest, ModelResponse
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.settings import ModelSettings

__all__ = ("CodexResponsesModel",)


class CodexResponsesModel(OpenAIResponsesModel):
    def __init__(
        self,
        model_name: str,
        *,
        default_instructions: str,
        provider: Any = "openai",
        profile: Any = None,
        settings: ModelSettings | None = None,
    ) -> None:
        self._default_instructions = default_instructions
        super().__init__(
            model_name,
            provider=provider,
            profile=profile,
            settings=settings,
        )

    def _with_default_instructions(
        self,
        messages: Sequence[ModelRequest | ModelResponse],
        model_request_parameters: ModelRequestParameters,
    ) -> list[ModelRequest | ModelResponse]:
        resolved = super()._get_instruction_parts(messages, model_request_parameters)
        if resolved:
            return list(messages)
        return [ModelRequest(parts=(), instructions=self._default_instructions), *messages]

    async def request(
        self,
        messages: list[ModelRequest | ModelResponse],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        prepared_messages = self._with_default_instructions(messages, model_request_parameters)
        async with self.request_stream(
            prepared_messages,
            model_settings,
            model_request_parameters,
        ) as streamed_response:
            async for _ in streamed_response:
                pass
            return streamed_response.get()

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelRequest | ModelResponse],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: Any | None = None,
    ) -> AsyncIterator[Any]:
        prepared_messages = self._with_default_instructions(messages, model_request_parameters)
        async with super().request_stream(
            prepared_messages,
            model_settings,
            model_request_parameters,
            run_context=run_context,
        ) as streamed_response:
            yield streamed_response
