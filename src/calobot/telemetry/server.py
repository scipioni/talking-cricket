"""FastAPI web server serving the telemetry WebSockets stream, HTTP endpoints, and the React SPA.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any

import secrets
import urllib.parse
import httpx2 as httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Response, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from calobot.settings import get_settings
from calobot.telemetry.auth import sign_session_token, verify_session_token
from calobot.telemetry.bus import event_bus
from calobot.telemetry.history import telemetry_history
from calobot.telemetry.scrub import anonymize_chat_id, scrub_telemetry_event

logger = logging.getLogger(__name__)

SESSION_SECRET = get_settings().session_secret_key or secrets.token_hex(32)

async def verify_admin_session(session_token: str | None = Cookie(None)) -> str:
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    email = verify_session_token(session_token, SESSION_SECRET)
    if not email:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return email

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
async def list_sessions(email: str = Depends(verify_admin_session)) -> list[dict[str, Any]]:
    """List all active chat sessions sorted by recency."""
    return telemetry_history.list_active_sessions()


@app.get("/api/sessions/{chat_id}/events")
async def get_session_events(chat_id: int, email: str = Depends(verify_admin_session)) -> list[dict[str, Any]]:
    """Get raw recorded events for a given chat_id."""
    events = telemetry_history.get_events(chat_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"No telemetry records found for chat_id={chat_id}")
    return events


@app.get("/api/export/{chat_id}")
async def export_session(chat_id: int, email: str = Depends(verify_admin_session)) -> dict[str, Any]:
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
async def websocket_endpoint(websocket: WebSocket, session_token: str | None = Cookie(None)) -> None:
    """Stream live telemetry events to connected dashboard clients via WebSocket."""
    if not session_token or not verify_session_token(session_token, SESSION_SECRET):
        await websocket.accept()
        await websocket.send_json({"error": "Unauthorized"})
        await websocket.close(code=4001)
        return

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


@app.get("/api/public/metrics")
async def get_public_metrics() -> dict[str, Any]:
    """Get aggregated anonymized operational metrics and scrubbed events for public dashboard."""
    active_sessions = telemetry_history.list_active_sessions()

    latencies: dict[str, list[float]] = {}
    intents: dict[str, int] = {}
    all_events: list[dict[str, Any]] = []

    for chat_id, deque_events in telemetry_history._history.items():
        for event in deque_events:
            all_events.append(event)
            if event.get("type") == "llm_transaction":
                step = event.get("step")
                latency = event.get("latency_seconds")
                if step and latency is not None:
                    latencies.setdefault(step, []).append(latency)

                if step == "classify" and event.get("response_parsed"):
                    parsed = event.get("response_parsed")
                    if isinstance(parsed, dict):
                        intent = parsed.get("intent")
                        if intent:
                            intents[intent] = intents.get(intent, 0) + 1

    avg_latencies = {step: sum(vals) / len(vals) for step, vals in latencies.items() if vals}

    # Sort all events by timestamp and grab the last 50
    sorted_events = sorted(all_events, key=lambda e: e.get("timestamp", ""), reverse=False)
    recent_scrubbed = [scrub_telemetry_event(e) for e in sorted_events[-50:]]

    scrubbed_sessions = []
    for s in active_sessions:
        scrubbed_sessions.append(
            {
                "chat_id": anonymize_chat_id(s["chat_id"]),
                "last_active": s["last_active"],
                "event_count": s["event_count"],
            }
        )

    return {
        "active_sessions_count": len(active_sessions),
        "avg_latencies": avg_latencies,
        "intent_distribution": intents,
        "sessions": scrubbed_sessions,
        "recent_events": recent_scrubbed,
    }


@app.websocket("/telemetry/public/ws")
async def public_websocket_endpoint(websocket: WebSocket) -> None:
    """Stream live, fully scrubbed telemetry events to unauthenticated connected clients via WebSocket."""
    await websocket.accept()
    logger.info("New public telemetry dashboard client connected via WebSocket.")

    queue = event_bus.subscribe()
    try:
        while True:
            event = await queue.get()
            scrubbed_event = scrub_telemetry_event(event)
            await websocket.send_json(scrubbed_event)
            queue.task_done()
    except WebSocketDisconnect:
        logger.info("Public telemetry dashboard client disconnected.")
    except Exception as exc:
        logger.warning("Error in public telemetry WebSocket session: %s", exc)
    finally:
        event_bus.unsubscribe(queue)


# Conditional mounting of Vite React SPA production assets
telemetry_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(telemetry_dir, "frontend", "dist")


@app.get("/api/auth/login")
async def login(request: Request) -> RedirectResponse:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured on this server.")

    state = secrets.token_hex(16)
    params = {
        "response_type": "code",
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "scope": "openid email",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

    response = RedirectResponse(auth_url)
    response.set_cookie(
        "oauth_state",
        state,
        httponly=True,
        secure=False,
        max_age=600,
        samesite="lax",
    )
    return response


@app.get("/api/auth/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    oauth_state: str | None = Cookie(None),
) -> Response:
    settings = get_settings()
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state.")

    if not oauth_state or state != oauth_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter (CSRF protection failed).")

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient() as client:
            token_res = await client.post(token_url, data=data)
            token_res.raise_for_status()
            token_data = token_res.json()
    except Exception as exc:
        logger.error("Failed to exchange OAuth code: %s", exc)
        raise HTTPException(status_code=400, detail="Failed to authenticate with Google.")

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token returned from Google.")

    userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
    try:
        async with httpx.AsyncClient() as client:
            user_res = await client.get(
                userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
            )
            user_res.raise_for_status()
            user_info = user_res.json()
    except Exception as exc:
        logger.error("Failed to fetch Google user info: %s", exc)
        raise HTTPException(status_code=400, detail="Failed to fetch Google user profile.")

    email = user_info.get("email")
    email_verified = user_info.get("email_verified")

    if not email or not email_verified:
        raise HTTPException(status_code=400, detail="Failed to retrieve a verified Google email.")

    allowed_emails = settings.allowed_admin_emails
    whitelist = [allowed_emails] if isinstance(allowed_emails, str) else allowed_emails

    if email not in whitelist:
        logger.warning("Unauthorized login attempt from email: %s", email)
        raise HTTPException(status_code=403, detail="Email is not authorized to access this private dashboard.")

    session_token = sign_session_token(email, SESSION_SECRET)

    response = RedirectResponse("/private")
    response.set_cookie(
        "session_token",
        session_token,
        httponly=True,
        secure=False,
        max_age=86400 * 7,
        samesite="lax",
    )
    response.delete_cookie("oauth_state")
    return response


@app.get("/api/auth/session")
async def get_session(session_token: str | None = Cookie(None)) -> dict[str, Any]:
    if not session_token:
        return {"authenticated": False, "email": None}
    email = verify_session_token(session_token, SESSION_SECRET)
    if not email:
        return {"authenticated": False, "email": None}
    return {"authenticated": True, "email": email}


@app.post("/api/auth/logout")
async def logout() -> Response:
    response = JSONResponse({"status": "success"})
    response.delete_cookie("session_token")
    return response


@app.get("/private")
async def serve_private_app() -> Response:
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="SPA index.html not found.")


if os.path.exists(static_dir):
    logger.info("Mounting telemetry frontend static folder from: %s", static_dir)
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning("Telemetry static folder %r not found. Dashboard won't be served.", static_dir)
