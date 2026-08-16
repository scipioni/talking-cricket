"""OpenAI-compatible gateway with schema-validated, retried calls (tasks.md 4.1-4.4).

design.md - The interpretation pipeline: schemas stay small and flat, validation
failures retry with the error text fed back, and exhaustion or transport failure
becomes one of the two typed errors in llm/errors.py rather than a raw exception.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from calobot.llm.content import ImageContent, MessageContent, TextContent
from calobot.llm.errors import LLMUnavailableError, LLMValidationExhaustedError
from calobot.settings import Settings

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


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
    ) -> SchemaT:
        """Raises LLMUnavailableError on transport/timeout failure, and
        LLMValidationExhaustedError when the model never returns schema-valid JSON
        within the configured retry limit."""
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
                }
            )
        raise LLMValidationExhaustedError(step) from last_error
