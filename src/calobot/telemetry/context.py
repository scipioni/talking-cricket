"""Task-local telemetry context tracking using contextvars.

Enables causal tracing across asynchronous boundaries, ensuring downstream calls (such as
LLM gateway invocations) are correlated back to the originating Telegram update.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Generator
from contextlib import contextmanager

# Context variable tracking the active chat_id (int)
active_chat_id: contextvars.ContextVar[int] = contextvars.ContextVar("active_chat_id")

# Context variable tracking a unique session ID (str) for this specific turn
active_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("active_session_id")


@contextmanager
def bind_telemetry_context(chat_id: int, session_id: str | None = None) -> Generator[None, None, None]:
    """Context manager to bind active chat_id and session_id.

    Generates a random UUID session_id if none is supplied.
    Resets the contextvars on exit.
    """
    token_chat = active_chat_id.set(chat_id)
    token_session = active_session_id.set(session_id or str(uuid.uuid4()))
    try:
        yield
    finally:
        active_chat_id.reset(token_chat)
        active_session_id.reset(token_session)
