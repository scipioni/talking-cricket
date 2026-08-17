"""OpenAI-compatible gateway with schema-validated, retried calls (tasks.md 4.1-4.4).

design.md - The interpretation pipeline: schemas stay small and flat, validation
failures retry with the error text fed back, and exhaustion or transport failure
becomes one of the two typed errors in llm/errors.py rather than a raw exception.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from calobot.llm.content import ImageContent, MessageContent, TextContent
from calobot.llm.errors import LLMUnavailableError, LLMValidationExhaustedError
from calobot.settings import Settings

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)
ArgsT = TypeVar("ArgsT", bound=BaseModel)


@dataclass(frozen=True)
class ToolDefinition:
    """One tool offered to an agentic call. `args_schema` validates the model's
    arguments before `handler` runs (specs/message-ingestion - Invalid retrieval
    arguments from the model); `handler` returns a JSON-serializable dict, which is
    both fed back to the model as the tool result and accumulated in `GatherResult`."""

    name: str
    description: str
    args_schema: type[BaseModel]
    handler: Callable[[BaseModel], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolCallResult:
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class GatherResult:
    """The outcome of one `call_agentic` loop. `exhausted` is True only when the
    round bound was reached without the model signalling it had enough
    (specs/advice-agent - The agent's work is bounded); it is False both when the
    model used no tool and when it used some and then stopped on its own."""

    tool_results: list[ToolCallResult] = field(default_factory=list)
    rounds_used: int = 0
    exhausted: bool = False
    # Shared with the caller's follow-up `call_structured` narration call via its
    # `extra_telemetry`, so a monitor can group the whole agent turn under one id
    # (design.md - Group an agent turn in telemetry with a correlation id).
    agent_turn_id: str = ""


def _content_to_openai_parts(content: MessageContent) -> list[dict[str, Any]]:
    if isinstance(content, TextContent):
        return [{"type": "text", "text": content.text}]
    if isinstance(content, ImageContent):
        parts: list[dict[str, Any]] = []
        if content.caption:
            parts.append({"type": "text", "text": content.caption})
        parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{content.mime_type};base64,{content.base64_data}"
                },
            }
        )
        return parts
    raise TypeError(f"unsupported content type: {type(content)!r}")


class LLMGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = openai.AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    async def call_structured(
        self,
        *,
        step: str,
        system_prompt: str,
        content: MessageContent,
        schema: type[SchemaT],
        extra_telemetry: dict[str, Any] | None = None,
    ) -> SchemaT:
        """Raises LLMUnavailableError on transport/timeout failure, and
        LLMValidationExhaustedError when the model never returns schema-valid JSON
        within the configured retry limit.

        `extra_telemetry` is merged into every published `llm_transaction` event -
        used by `call_agentic`'s narration call to carry the same `agent_turn_id` as
        the gather rounds that preceded it, so a monitor can group one agent turn
        (design.md - Group an agent turn in telemetry with a correlation id)."""
        model = self._settings.model_for_step(step)
        temperature = self._settings.temperature_for_step(step)
        retry_limit = self._settings.llm_retry_limit

        from calobot.telemetry.bus import event_bus
        from calobot.telemetry.context import active_chat_id, active_session_id

        chat_id = active_chat_id.get(None)
        session_id = active_session_id.get(None)

        prompt_text = ""
        if isinstance(content, TextContent):
            prompt_text = content.text
        elif isinstance(content, ImageContent):
            prompt_text = f"[Image Content] Caption: {content.caption or 'None'}"

        start_time = dt.datetime.now(dt.UTC)
        validation_attempts: list[dict[str, Any]] = []

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _content_to_openai_parts(content)},
        ]

        last_error: Exception | None = None
        for attempt in range(retry_limit + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    messages=messages,  # type: ignore[call-overload]
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.__name__,
                            "schema": schema.model_json_schema(),
                            "strict": False,
                        },
                    },
                )
            except (openai.APIConnectionError, openai.APITimeoutError) as exc:
                logger.warning("llm endpoint unreachable/timed out on step=%s: %s", step, exc)
                if chat_id is not None:
                    event_bus.publish(
                        {
                            "type": "llm_transaction",
                            "chat_id": chat_id,
                            "session_id": session_id,
                            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                            "step": step,
                            "model": model,
                            "temperature": temperature,
                            "system_prompt": system_prompt,
                            "prompt": prompt_text,
                            "schema_name": schema.__name__,
                            "attempts_count": attempt + 1,
                            "success": False,
                            "error": f"LLM Connection/Timeout Error: {exc}",
                            **(extra_telemetry or {}),
                        }
                    )
                raise LLMUnavailableError(step) from exc
            except openai.APIStatusError as exc:
                logger.warning("llm endpoint error on step=%s: %s", step, exc)
                if chat_id is not None:
                    event_bus.publish(
                        {
                            "type": "llm_transaction",
                            "chat_id": chat_id,
                            "session_id": session_id,
                            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                            "step": step,
                            "model": model,
                            "temperature": temperature,
                            "system_prompt": system_prompt,
                            "prompt": prompt_text,
                            "schema_name": schema.__name__,
                            "attempts_count": attempt + 1,
                            "success": False,
                            "error": f"LLM API Status Error ({exc.status_code}): {exc.message}",
                            **(extra_telemetry or {}),
                        }
                    )
                raise LLMUnavailableError(step) from exc

            raw = response.choices[0].message.content or ""
            try:
                parsed = json.loads(raw)
                validated = schema.model_validate(parsed)

                if chat_id is not None:
                    latency = (dt.datetime.now(dt.UTC) - start_time).total_seconds()
                    event_bus.publish(
                        {
                            "type": "llm_transaction",
                            "chat_id": chat_id,
                            "session_id": session_id,
                            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                            "step": step,
                            "model": model,
                            "temperature": temperature,
                            "system_prompt": system_prompt,
                            "prompt": prompt_text,
                            "schema_name": schema.__name__,
                            "schema_json": schema.model_json_schema(),
                            "response_raw": raw,
                            "response_parsed": parsed,
                            "attempts_count": attempt + 1,
                            "validation_attempts": validation_attempts,
                            "latency_seconds": latency,
                            "success": True,
                            **(extra_telemetry or {}),
                        }
                    )
                return validated
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                logger.info(
                    "llm output failed validation on step=%s attempt=%s: %s",
                    step,
                    attempt,
                    exc,
                )
                validation_attempts.append(
                    {
                        "attempt": attempt + 1,
                        "raw_response": raw,
                        "error": str(exc),
                    }
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous response did not match the required schema. "
                            f"Validation error: {exc}. Reply again with corrected JSON only."
                        ),
                    }
                )
                continue

        if chat_id is not None:
            latency = (dt.datetime.now(dt.UTC) - start_time).total_seconds()
            event_bus.publish(
                {
                    "type": "llm_transaction",
                    "chat_id": chat_id,
                    "session_id": session_id,
                    "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                    "step": step,
                    "model": model,
                    "temperature": temperature,
                    "system_prompt": system_prompt,
                    "prompt": prompt_text,
                    "schema_name": schema.__name__,
                    "schema_json": schema.model_json_schema(),
                    "attempts_count": retry_limit + 1,
                    "validation_attempts": validation_attempts,
                    "latency_seconds": latency,
                    "success": False,
                    "error": f"Validation limit exhausted: {last_error}",
                    **(extra_telemetry or {}),
                }
            )
        raise LLMValidationExhaustedError(step) from last_error

    async def call_agentic(
        self,
        *,
        step: str,
        system_prompt: str,
        content: MessageContent,
        tools: list[ToolDefinition],
        max_rounds: int,
    ) -> GatherResult:
        """Drives a bounded tool-calling loop in-process: each round offers `tools` to
        the model, validates and runs whatever it requests, and feeds results back.
        The loop ends either when the model requests no tool call (`exhausted=False`)
        or when `max_rounds` is reached without that happening (`exhausted=True`) -
        never by raising (specs/advice-agent - The agent's work is bounded).

        Raises LLMUnavailableError on transport/timeout failure, exactly as
        `call_structured` does. A request for an unknown tool, or one whose
        arguments fail validation, does not raise: it is fed back to the model as a
        rejected call and costs one round (specs/message-ingestion - Invalid
        retrieval arguments from the model)."""
        model = self._settings.model_for_step(step)
        temperature = self._settings.temperature_for_step(step)
        by_name = {tool.name: tool for tool in tools}
        tools_payload = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.args_schema.model_json_schema(),
                },
            }
            for tool in tools
        ]

        from calobot.telemetry.bus import event_bus
        from calobot.telemetry.context import active_chat_id, active_session_id

        chat_id = active_chat_id.get(None)
        session_id = active_session_id.get(None)
        agent_turn_id = uuid.uuid4().hex

        prompt_text = content.text if isinstance(content, TextContent) else ""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _content_to_openai_parts(content)},
        ]

        tool_results: list[ToolCallResult] = []

        for round_index in range(max_rounds):
            start_time = dt.datetime.now(dt.UTC)
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    messages=messages,  # type: ignore[arg-type]
                    tools=tools_payload,  # type: ignore[arg-type]
                )
            except (openai.APIConnectionError, openai.APITimeoutError) as exc:
                logger.warning("llm endpoint unreachable/timed out on step=%s: %s", step, exc)
                if chat_id is not None:
                    event_bus.publish(
                        {
                            "type": "llm_transaction",
                            "chat_id": chat_id,
                            "session_id": session_id,
                            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                            "step": step,
                            "model": model,
                            "temperature": temperature,
                            "system_prompt": system_prompt,
                            "prompt": prompt_text,
                            "agent_turn_id": agent_turn_id,
                            "round_index": round_index,
                            "success": False,
                            "error": f"LLM Connection/Timeout Error: {exc}",
                        }
                    )
                raise LLMUnavailableError(step) from exc
            except openai.APIStatusError as exc:
                logger.warning("llm endpoint error on step=%s: %s", step, exc)
                if chat_id is not None:
                    event_bus.publish(
                        {
                            "type": "llm_transaction",
                            "chat_id": chat_id,
                            "session_id": session_id,
                            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                            "step": step,
                            "model": model,
                            "temperature": temperature,
                            "system_prompt": system_prompt,
                            "prompt": prompt_text,
                            "agent_turn_id": agent_turn_id,
                            "round_index": round_index,
                            "success": False,
                            "error": f"LLM API Status Error ({exc.status_code}): {exc.message}",
                        }
                    )
                raise LLMUnavailableError(step) from exc

            message = response.choices[0].message
            requested = list(getattr(message, "tool_calls", None) or [])
            latency = (dt.datetime.now(dt.UTC) - start_time).total_seconds()

            if chat_id is not None:
                event_bus.publish(
                    {
                        "type": "llm_transaction",
                        "chat_id": chat_id,
                        "session_id": session_id,
                        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                        "step": step,
                        "model": model,
                        "temperature": temperature,
                        "system_prompt": system_prompt,
                        "prompt": prompt_text,
                        "agent_turn_id": agent_turn_id,
                        "round_index": round_index,
                        "tool_name": ", ".join(tc.function.name for tc in requested) or None,
                        "latency_seconds": latency,
                        "success": True,
                    }
                )

            if not requested:
                return GatherResult(
                    tool_results=tool_results,
                    rounds_used=round_index + 1,
                    exhausted=False,
                    agent_turn_id=agent_turn_id,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in requested
                    ],
                }
            )

            for tool_call in requested:
                tool_response = await self._run_one_tool(tool_call, by_name)
                if isinstance(tool_response, ToolCallResult):
                    tool_results.append(tool_response)
                    result_content = json.dumps(tool_response.result)
                else:
                    result_content = json.dumps({"error": tool_response})
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": result_content}
                )

        return GatherResult(
            tool_results=tool_results,
            rounds_used=max_rounds,
            exhausted=True,
            agent_turn_id=agent_turn_id,
        )

    async def _run_one_tool(
        self, tool_call: Any, by_name: dict[str, ToolDefinition]
    ) -> ToolCallResult | str:
        """Returns the executed `ToolCallResult`, or a plain string explaining why the
        call was refused - refusal is not an error, it is fed back to the model."""
        tool = by_name.get(tool_call.function.name)
        if tool is None:
            return f"unknown tool: {tool_call.function.name!r}"
        try:
            raw_args = json.loads(tool_call.function.arguments or "{}")
            validated_args = tool.args_schema.model_validate(raw_args)
        except (json.JSONDecodeError, ValidationError) as exc:
            return f"arguments rejected: {exc}"
        try:
            result = await tool.handler(validated_args)
        except Exception as exc:
            # Fed back to the model as a plain refusal, never as exception text or a
            # stack trace (specs/advice-agent - The agent's work is bounded: "A
            # retrieval fails"). The model sees only that the call did not produce
            # data, exactly as it would see any other empty result.
            logger.warning("tool handler failed for %s: %s", tool.name, exc)
            return "the tool failed and returned no data"
        return ToolCallResult(tool=tool.name, arguments=raw_args, result=result)
