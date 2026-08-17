from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import openai
import pytest
from pydantic import BaseModel

from calobot.llm.content import TextContent
from calobot.llm.errors import LLMUnavailableError, LLMValidationExhaustedError
from calobot.llm.gateway import LLMGateway, ToolDefinition
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


# -- call_agentic ----------------------------------------------------------


class LookupArgs(BaseModel):
    day: str


def _tool_call(name: str, arguments: dict, call_id: str = "call_1"):
    return SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments))
    )


def _tool_calls_response(*calls):
    message = SimpleNamespace(content=None, tool_calls=list(calls))
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _no_tool_calls_response(content: str = ""):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _make_lookup_tool(handler):
    return ToolDefinition(
        name="lookup",
        description="looks something up",
        args_schema=LookupArgs,
        handler=handler,
    )


async def test_agentic_call_runs_a_valid_tool_then_stops():
    gateway = _make_gateway()
    calls_made: list[LookupArgs] = []

    async def handler(args: LookupArgs) -> dict:
        calls_made.append(args)
        return {"kcal": 1234}

    gateway._client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_calls_response(_tool_call("lookup", {"day": "2026-08-17"})),
            _no_tool_calls_response("ok, ho quello che serve"),
        ]
    )

    result = await gateway.call_agentic(
        step="advice_gather",
        system_prompt="sys",
        content=TextContent(text="quante calorie ho mangiato oggi?"),
        tools=[_make_lookup_tool(handler)],
        max_rounds=4,
    )

    assert not result.exhausted
    assert result.rounds_used == 2
    assert len(result.tool_results) == 1
    assert result.tool_results[0].tool == "lookup"
    assert result.tool_results[0].result == {"kcal": 1234}
    assert calls_made == [LookupArgs(day="2026-08-17")]


async def test_agentic_call_refuses_unknown_tool_without_running_it():
    gateway = _make_gateway()
    handler = AsyncMock()

    gateway._client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_calls_response(_tool_call("delete_everything", {})),
            _no_tool_calls_response(),
        ]
    )

    result = await gateway.call_agentic(
        step="advice_gather",
        system_prompt="sys",
        content=TextContent(text="qualcosa"),
        tools=[_make_lookup_tool(handler)],
        max_rounds=4,
    )

    assert not result.exhausted
    assert result.tool_results == []
    handler.assert_not_awaited()


async def test_agentic_call_rejects_invalid_arguments_without_running_the_tool():
    gateway = _make_gateway()
    handler = AsyncMock()

    gateway._client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_calls_response(_tool_call("lookup", {"wrong_field": 1})),
            _no_tool_calls_response(),
        ]
    )

    result = await gateway.call_agentic(
        step="advice_gather",
        system_prompt="sys",
        content=TextContent(text="qualcosa"),
        tools=[_make_lookup_tool(handler)],
        max_rounds=4,
    )

    assert not result.exhausted
    assert result.tool_results == []
    handler.assert_not_awaited()


async def test_agentic_call_reports_exhausted_when_bound_reached():
    gateway = _make_gateway()

    async def handler(args: LookupArgs) -> dict:
        return {"kcal": 1}

    gateway._client.chat.completions.create = AsyncMock(
        return_value=_tool_calls_response(_tool_call("lookup", {"day": "2026-08-17"}))
    )

    result = await gateway.call_agentic(
        step="advice_gather",
        system_prompt="sys",
        content=TextContent(text="qualcosa"),
        tools=[_make_lookup_tool(handler)],
        max_rounds=3,
    )

    assert result.exhausted
    assert result.rounds_used == 3
    assert len(result.tool_results) == 3


async def test_agentic_call_timeout_raises_unavailable_error():
    gateway = _make_gateway()
    gateway._client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=SimpleNamespace())
    )

    with pytest.raises(LLMUnavailableError):
        await gateway.call_agentic(
            step="advice_gather",
            system_prompt="sys",
            content=TextContent(text="qualcosa"),
            tools=[_make_lookup_tool(AsyncMock())],
            max_rounds=4,
        )
