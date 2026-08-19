"""JSONL Logger for tracking logical user interactions in a single row.

Compiles telemetry events (incoming updates, bot responses, LLM transactions)
into a structured representation of a single turn and writes it to a file.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

from calobot.settings import Settings

logger = logging.getLogger(__name__)


def _sync_write(path: Path, record: dict[str, Any]) -> None:
    """Synchronous part of writing to the JSONL file, executed in a thread pool."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to write interaction log to %s: %s", path, exc)


async def write_interaction_log(
    *,
    chat_id: int,
    session_id: str,
    start_time: dt.datetime,
    success: bool,
    error_message: str | None,
    events: list[dict[str, Any]],
    settings: Settings,
) -> None:
    """Asynchronously compile and write a logical user interaction row to the JSONL file."""
    if not settings.jsonl_log_enabled:
        return

    end_time = dt.datetime.now(dt.UTC)
    duration_seconds = (end_time - start_time).total_seconds()

    # Extract user message/update details
    user_message = {}
    incoming_updates = [e for e in events if e.get("type") == "incoming_update"]
    if incoming_updates:
        ue = incoming_updates[0]
        user_message = {
            "update_id": ue.get("update_id"),
            "timestamp": ue.get("timestamp"),
            "text": ue.get("text"),
            "callback_data": ue.get("callback_data"),
            "has_image": ue.get("has_image", False),
            "username": ue.get("username"),
        }

    # Extract bot responses
    bot_responses = []
    outgoing_responses = [e for e in events if e.get("type") == "outgoing_response"]
    for re in outgoing_responses:
        bot_responses.append({
            "method": re.get("method"),
            "text": re.get("text"),
            "options": re.get("options"),
            "has_image": re.get("has_image", False),
            "timestamp": re.get("timestamp"),
        })

    # Extract LLM transactions
    llm_interactions = []
    llm_transactions = [e for e in events if e.get("type") == "llm_transaction"]
    for le in llm_transactions:
        llm_interactions.append({
            "step": le.get("step"),
            "model": le.get("model"),
            "temperature": le.get("temperature"),
            "prompt": le.get("prompt"),
            "success": le.get("success"),
            "error": le.get("error"),
            "response_raw": le.get("response_raw"),
            "response_parsed": le.get("response_parsed"),
            "latency_seconds": le.get("latency_seconds"),
            "timestamp": le.get("timestamp"),
        })

    # Flat activities sequence
    activities = []
    for event in events:
        activities.append({
            "type": event.get("type"),
            "timestamp": event.get("timestamp"),
            "details": {
                k: v
                for k, v in event.items()
                if k not in ("type", "timestamp", "chat_id", "session_id")
            },
        })

    record = {
        "session_id": session_id,
        "chat_id": chat_id,
        "timestamp": start_time.isoformat(),
        "duration_seconds": duration_seconds,
        "status": "success" if success else "error",
        "error": error_message,
        "user_message": user_message,
        "bot_responses": bot_responses,
        "llm_interactions": llm_interactions,
        "activities": activities,
    }

    path = Path(settings.jsonl_log_path)
    await asyncio.to_thread(_sync_write, path, record)
