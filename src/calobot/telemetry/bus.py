"""Thread-safe, non-blocking asynchronous event bus for broadcasting real-time telemetry events.

Utilizes asyncio.Queue for multi-subscriber support, allowing WebSocket sessions 
and memory recorders to concurrently receive events.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryEventBus:
    def __init__(self) -> None:
        self._listeners: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Subscribe to the event bus. Returns an asyncio Queue."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._listeners.add(queue)
        logger.debug("New telemetry subscription created. Total listeners: %d", len(self._listeners))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Unsubscribe from the event bus."""
        self._listeners.discard(queue)
        logger.debug("Telemetry subscription removed. Total listeners: %d", len(self._listeners))

    def publish(self, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers synchronously and non-blocking."""
        from calobot.telemetry.context import active_interaction_events
        events_list = active_interaction_events.get(None)
        if events_list is not None:
            events_list.append(dict(event))

        if not self._listeners:
            return

        logger.debug("Broadcasting telemetry event type=%s", event.get("type"))
        for queue in self._listeners:
            try:
                queue.put_nowait(event)
            except Exception as exc:
                logger.warning("Failed to queue telemetry event: %s", exc)


# Global shared instance of the telemetry event bus for this process.
event_bus = TelemetryEventBus()
