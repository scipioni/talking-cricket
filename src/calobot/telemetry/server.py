"""FastAPI web server serving the telemetry WebSockets stream, HTTP endpoints, and the React SPA.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from calobot.telemetry.bus import event_bus
from calobot.telemetry.history import telemetry_history

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Calobot Activity Monitor API",
    description="Real-time WebSockets and HTTP APIs for Calobot chatbot observability",
)

# Enable CORS for local Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    """List all active chat sessions sorted by recency."""
    return telemetry_history.list_active_sessions()


@app.get("/api/sessions/{chat_id}/events")
async def get_session_events(chat_id: int) -> list[dict[str, Any]]:
    """Get raw recorded events for a given chat_id."""
    events = telemetry_history.get_events(chat_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"No telemetry records found for chat_id={chat_id}")
    return events


@app.get("/api/export/{chat_id}")
async def export_session(chat_id: int) -> dict[str, Any]:
    """Export unified chronological activity timeline of a chat session, formatted for agent analysis."""
    events = telemetry_history.get_events(chat_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"No telemetry records found for chat_id={chat_id}")

    timeline: list[dict[str, Any]] = []
    for event in events:
        ev_type = event.get("type")
        timestamp = event.get("timestamp")

        if ev_type == "incoming_update":
            timeline.append(
                {
                    "timestamp": timestamp,
                    "event": "user_message",
                    "text": event.get("text", ""),
                    "has_image": event.get("has_image", False),
                    "username": event.get("username"),
                    "callback_data": event.get("callback_data"),
                }
            )
        elif ev_type == "outgoing_response":
            timeline.append(
                {
                    "timestamp": timestamp,
                    "event": "bot_message",
                    "text": event.get("text", ""),
                    "method": event.get("method"),
                    "options": event.get("options", {}),
                    "has_image": event.get("has_image", False),
                }
            )
        elif ev_type == "llm_transaction":
            timeline.append(
                {
                    "timestamp": timestamp,
                    "event": "llm_step",
                    "step": event.get("step"),
                    "model": event.get("model"),
                    "temperature": event.get("temperature"),
                    "system_prompt": event.get("system_prompt"),
                    "prompt": event.get("prompt"),
                    "schema_name": event.get("schema_name"),
                    "schema_json": event.get("schema_json"),
                    "response_raw": event.get("response_raw"),
                    "response_parsed": event.get("response_parsed"),
                    "attempts_count": event.get("attempts_count"),
                    "validation_attempts": event.get("validation_attempts", []),
                    "latency_seconds": event.get("latency_seconds"),
                    "success": event.get("success"),
                    "error": event.get("error"),
                    # Present only on advice-agent calls, so a monitor can group one
                    # agent turn (design.md - Group an agent turn in telemetry with a
                    # correlation id). None on every other step, by construction.
                    "agent_turn_id": event.get("agent_turn_id"),
                    "round_index": event.get("round_index"),
                    "tool_name": event.get("tool_name"),
                }
            )

    return {
        "chat_id": chat_id,
        "exported_at": dt.datetime.now(dt.UTC).isoformat(),
        "timeline": timeline,
    }


@app.websocket("/telemetry/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Stream live telemetry events to connected dashboard clients via WebSocket."""
    await websocket.accept()
    logger.info("New telemetry dashboard client connected via WebSocket.")

    queue = event_bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            queue.task_done()
    except WebSocketDisconnect:
        logger.info("Telemetry dashboard client disconnected.")
    except Exception as exc:
        logger.warning("Error in telemetry WebSocket session: %s", exc)
    finally:
        event_bus.unsubscribe(queue)


# Conditional mounting of Vite React SPA production assets
telemetry_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(telemetry_dir, "frontend", "dist")

if os.path.exists(static_dir):
    logger.info("Mounting telemetry frontend static folder from: %s", static_dir)
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning("Telemetry static folder %r not found. Dashboard won't be served.", static_dir)
