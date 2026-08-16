from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import openai
import pytest
from pydantic import BaseModel

from calobot.llm.content import TextContent
from calobot.llm.errors import LLMUnavailableError, LLMValidationExhaustedError
from calobot.llm.gateway import LLMGateway
from calobot.settings import Settings


class DummySchema(BaseModel):
    intent: str
    grams: float


def _make_gateway() -> LLMGateway:
    settings = Settings(telegram_bot_token="x", llm_retry_limit=2)  # type: ignore[call-arg]
    return LLMGateway(settings)


def _fake_response(content: str):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


async def test_valid_output_returns_parsed_schema():
    gateway = _make_gateway()
    gateway._client.chat.completions.create = AsyncMock(
        return_value=_fake_response(json.dumps({"intent": "food", "grams": 10.0}))
    )

    result = await gateway.call_structured(
        step="extract",
        system_prompt="sys",
        content=TextContent(text="10g di noci"),
        schema=DummySchema,
    )

    assert result.intent == "food"
    assert result.grams == 10.0
    assert gateway._client.chat.completions.create.await_count == 1


async def test_malformed_output_recovered_by_retry():
    gateway = _make_gateway()
    gateway._client.chat.completions.create = AsyncMock(
        side_effect=[
            _fake_response("not json at all"),
            _fake_response(json.dumps({"intent": "food", "grams": 10.0})),
        ]
    )

    result = await gateway.call_structured(
        step="extract",
        system_prompt="sys",
        content=TextContent(text="10g di noci"),
        schema=DummySchema,
    )

    assert result.intent == "food"
    assert gateway._client.chat.completions.create.await_count == 2


async def test_retries_exhausted_raises_typed_error():
    gateway = _make_gateway()
    gateway._client.chat.completions.create = AsyncMock(return_value=_fake_response("garbage"))

    with pytest.raises(LLMValidationExhaustedError):
        await gateway.call_structured(
            step="extract",
            system_prompt="sys",
            content=TextContent(text="10g di noci"),
            schema=DummySchema,
        )

    assert gateway._client.chat.completions.create.await_count == 3  # 1 + retry_limit(2)


async def test_timeout_raises_unavailable_error():
    gateway = _make_gateway()
    gateway._client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=SimpleNamespace())
    )

    with pytest.raises(LLMUnavailableError):
        await gateway.call_structured(
            step="extract",
            system_prompt="sys",
            content=TextContent(text="10g di noci"),
            schema=DummySchema,
        )
