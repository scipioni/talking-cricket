"""Unit and integration tests for telemetry context-propagation, event-bus, history, and FastAPI.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from calobot.telemetry.bus import TelemetryEventBus, event_bus
from calobot.telemetry.context import active_chat_id, active_session_id, bind_telemetry_context
from calobot.telemetry.history import InMemoryTelemetryHistory, telemetry_history
from calobot.telemetry.server import app


def test_telemetry_event_bus() -> None:
    """Verify that the event bus correctly handles subscribe, publish, and unsubscribe."""
    bus = TelemetryEventBus()
    queue = bus.subscribe()

    event = {"type": "test_event", "chat_id": 123}
    bus.publish(event)

    # Confirm it reached the queue
    assert queue.qsize() == 1
    received = queue.get_nowait()
    assert received == event

    # Unsubscribe and publish again
    bus.unsubscribe(queue)
    bus.publish(event)
    assert queue.qsize() == 0


def test_context_propagation() -> None:
    """Verify that bind_telemetry_context sets and resets task-local contextvars correctly."""
    assert active_chat_id.get(None) is None
    assert active_session_id.get(None) is None

    with bind_telemetry_context(999, "my-session-123"):
        assert active_chat_id.get(None) == 999
        assert active_session_id.get(None) == "my-session-123"

    assert active_chat_id.get(None) is None
    assert active_session_id.get(None) is None


def test_in_memory_telemetry_history() -> None:
    """Verify that history deques respect the strict bounded size limits (FIFO eviction)."""
    history = InMemoryTelemetryHistory(max_events_per_chat=3)

    # Check empty states
    assert history.get_events(123) == []
    assert history.list_active_sessions() == []

    # Record first event
    event1 = {"type": "incoming_update", "chat_id": 123, "timestamp": "2026-08-16T12:00:00Z"}
    history.add_event(event1)

    assert history.get_events(123) == [event1]
    sessions = history.list_active_sessions()
    assert len(sessions) == 1
    assert sessions[0]["chat_id"] == 123
    assert sessions[0]["event_count"] == 1

    # Add 4 more events to trigger FIFO eviction (limit=3)
    for seq in range(2, 6):
        history.add_event(
            {
                "type": "incoming_update",
                "chat_id": 123,
                "timestamp": f"2026-08-16T12:00:0{seq}Z",
                "seq": seq,
            }
        )

    # Eviction check
    events = history.get_events(123)
    assert len(events) == 3
    assert [e["seq"] for e in events] == [3, 4, 5]


def test_fastapi_endpoints() -> None:
    """Verify HTTP endpoints list, retrieve, and format sessions/timeline exports correctly."""
    telemetry_history._history.clear()
    telemetry_history._last_active.clear()

    event = {
        "type": "incoming_update",
        "chat_id": 123,
        "text": "stasera pizza",
        "timestamp": "2026-08-16T12:00:00Z",
    }
    telemetry_history.add_event(event)

    client = TestClient(app)

    # 1. Test Sessions Listing
    response = client.get("/api/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["chat_id"] == 123
    assert data[0]["event_count"] == 1

    # 2. Test Events Fetching
    response = client.get("/api/sessions/123/events")
    assert response.status_code == 200
    assert response.json() == [event]

    # 3. Test Activity Timeline Export Formatting
    response = client.get("/api/export/123")
    assert response.status_code == 200
    export = response.json()
    assert export["chat_id"] == 123
    assert "exported_at" in export
    assert len(export["timeline"]) == 1

    item = export["timeline"][0]
    assert item["event"] == "user_message"
    assert item["text"] == "stasera pizza"


def test_fastapi_websocket() -> None:
    """Verify that active WebSocket clients receive published bus events in real time."""
    client = TestClient(app)

    with client.websocket_connect("/telemetry/ws") as websocket:
        event = {"type": "test_broadcast", "chat_id": 789}
        event_bus.publish(event)

        received = websocket.receive_json()
        assert received == event
