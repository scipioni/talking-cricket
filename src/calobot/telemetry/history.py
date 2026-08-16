"""In-memory telemetry history storage utilizing bounded deques.

Maintains the last N events per chat_id to keep memory usage bounded and avoid writing
unnecessary diagnostic logs into the primary SQLite database.
"""

from __future__ import annotations

import asyncio
import collections
import datetime as dt
import logging
from typing import Any

logger = logging.getLogger(__name__)


class InMemoryTelemetryHistory:
    def __init__(self, max_events_per_chat: int = 100) -> None:
        self.max_events = max_events_per_chat
        # Map: chat_id (int) -> deque of telemetry event dicts
        self._history: dict[int, collections.deque[dict[str, Any]]] = {}
        # Map: chat_id (int) -> last updated timezone-aware UTC datetime
        self._last_active: dict[int, dt.datetime] = {}
        # Background listener task that listens to the central event bus
        self._listener_task: asyncio.Task[None] | None = None

    def add_event(self, event: dict[str, Any]) -> None:
        """Add a telemetry event to the bounded history for its associated chat_id."""
        chat_id = event.get("chat_id")
        if chat_id is None:
            return

        try:
            chat_id = int(chat_id)
        except (ValueError, TypeError):
            logger.warning("Telemetry event contains non-integral chat_id: %r", chat_id)
            return

        if chat_id not in self._history:
            self._history[chat_id] = collections.deque(maxlen=self.max_events)

        self._history[chat_id].append(event)
        self._last_active[chat_id] = dt.datetime.now(dt.UTC)

    def get_events(self, chat_id: int) -> list[dict[str, Any]]:
        """Retrieve all recorded telemetry events for a given chat_id (oldest first)."""
        if chat_id not in self._history:
            return []
        return list(self._history[chat_id])

    def list_active_sessions(self) -> list[dict[str, Any]]:
        """List active session chat_ids with metadata, sorted by recency (newest first)."""
        sessions = []
        for chat_id, last_time in self._last_active.items():
            event_count = len(self._history.get(chat_id, []))
            sessions.append(
                {
                    "chat_id": chat_id,
                    "last_active": last_time.isoformat(),
                    "event_count": event_count,
                }
            )
        return sorted(sessions, key=lambda s: s["last_active"], reverse=True)

    def start_listening(self) -> None:
        """Start a background asyncio task to subscribe to and ingest events from the Event Bus."""
        if self._listener_task is not None:
            return

        from calobot.telemetry.bus import event_bus

        queue = event_bus.subscribe()

        async def _listen_loop() -> None:
            logger.info("Telemetry history collector loop started.")
            try:
                while True:
                    event = await queue.get()
                    self.add_event(event)
                    queue.task_done()
            except asyncio.CancelledError:
                logger.info("Telemetry history collector loop stopped.")
            finally:
                event_bus.unsubscribe(queue)

        self._listener_task = asyncio.create_task(_listen_loop())

    def stop_listening(self) -> None:
        """Stop the background collector task."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None


# Shared process-wide singleton instance of the history manager.
telemetry_history = InMemoryTelemetryHistory()
