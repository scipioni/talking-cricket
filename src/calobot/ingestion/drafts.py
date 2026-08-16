"""Draft persistence. Drafts live in the database, not aiogram FSM memory, so a
pending clarification survives a Swarm restart (design.md - Drafts and the
clarification loop; specs/message-ingestion - Draft persistence).

Payload shape (JSON): {"items": [ {..fields.., "resolved": {...}} ], "current_index": 0}
Each item dict is opaque to this module - the food/activity planners own its shape
and read/write "resolved" themselves. This module only manages the envelope:
which item is current, and the awaiting_field/question/options being asked about it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import DraftIntent, PendingDraft
from calobot.persistence.timeutil import utcnow


async def get_open_draft(session: AsyncSession, user_id: int) -> PendingDraft | None:
    result = await session.execute(select(PendingDraft).where(PendingDraft.user_id == user_id))
    return result.scalar_one_or_none()


async def create_draft(
    session: AsyncSession,
    user_id: int,
    intent: DraftIntent,
    items: list[dict[str, Any]],
) -> PendingDraft:
    existing = await get_open_draft(session, user_id)
    if existing is not None:
        await session.delete(existing)
        await session.flush()

    draft = PendingDraft(
        user_id=user_id,
        intent=intent,
        payload={"items": items, "current_index": 0},
    )
    session.add(draft)
    await session.flush()
    return draft


def current_item(draft: PendingDraft) -> dict[str, Any]:
    return draft.payload["items"][draft.payload["current_index"]]


def has_more_items(draft: PendingDraft) -> bool:
    return draft.payload["current_index"] < len(draft.payload["items"])


def all_items(draft: PendingDraft) -> list[dict[str, Any]]:
    return list(draft.payload["items"])


async def replace_current_item(
    session: AsyncSession, draft: PendingDraft, new_item: dict[str, Any]
) -> None:
    items = list(draft.payload["items"])
    items[draft.payload["current_index"]] = new_item
    draft.payload = {**draft.payload, "items": items}
    await session.flush()


async def set_awaiting_field(session: AsyncSession, draft: PendingDraft, field: str | None) -> None:
    draft.awaiting_field = field
    await session.flush()


async def advance_to_next_item(session: AsyncSession, draft: PendingDraft) -> None:
    draft.payload = {**draft.payload, "current_index": draft.payload["current_index"] + 1}
    draft.awaiting_field = None
    await session.flush()


async def discard_draft(session: AsyncSession, user_id: int) -> bool:
    draft = await get_open_draft(session, user_id)
    if draft is None:
        return False
    await session.delete(draft)
    await session.flush()
    return True


def is_expired(draft: PendingDraft, expiry_minutes: int, now: dt.datetime | None = None) -> bool:
    now = now or utcnow()
    updated_at = draft.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=dt.UTC)
    return (now - updated_at) > dt.timedelta(minutes=expiry_minutes)
