"""Task-local telemetry context tracking using contextvars.

Enables causal tracing across asynchronous boundaries, ensuring downstream calls (such as
LLM gateway invocations) are correlated back to the originating Telegram update.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

# Context variable tracking the active chat_id (int)
active_chat_id: contextvars.ContextVar[int] = contextvars.ContextVar("active_chat_id")

# Context variable tracking a unique session ID (str) for this specific turn
active_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("active_session_id")

# Context variable tracking accumulated events for the current user interaction turn
active_interaction_events: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "active_interaction_events", default=None
)

# Context variable tracking whether no-retention mode is active for the current task
active_no_retention: contextvars.ContextVar[bool] = contextvars.ContextVar("active_no_retention", default=False)

# In-memory global set of chat_ids currently in no-retention mode
no_retention_chats: set[int] = set()


@contextmanager
def bind_telemetry_context(
    chat_id: int,
    session_id: str | None = None,
    events: list[dict[str, Any]] | None = None,
) -> Generator[None, None, None]:
    """Context manager to bind active chat_id, session_id, and active_interaction_events.

    Generates a random UUID session_id if none is supplied.
    Resets the contextvars on exit.
    """
    token_chat = active_chat_id.set(chat_id)
    token_session = active_session_id.set(session_id or str(uuid.uuid4()))
    token_events = active_interaction_events.set(events)
    token_no_retention = active_no_retention.set(chat_id in no_retention_chats)
    try:
        yield
    finally:
        active_chat_id.reset(token_chat)
        active_session_id.reset(token_session)
        active_interaction_events.reset(token_events)
        active_no_retention.reset(token_no_retention)
