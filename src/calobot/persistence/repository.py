"""Repository functions. Every read filters deleted_at IS NULL by default, per
specs/entry-correction - Soft deletion: deleted entries must never contribute to a report."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import (
    ActivityEntry,
    ActivityLevelHistory,
    AdviceOutcome,
    AdviceRecord,
    AdviceSurface,
    AdviceTopic,
    FoodEntry,
    PendingDraft,
    User,
    WeightEntry,
)
from calobot.persistence.timeutil import utcnow


async def get_user_by_telegram_id(session: AsyncSession, telegram_user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, telegram_user_id: int) -> User:
    user = User(telegram_user_id=telegram_user_id)
    session.add(user)
    await session.flush()
    return user


async def get_open_draft(session: AsyncSession, user_id: int) -> PendingDraft | None:
    result = await session.execute(
        select(PendingDraft).where(PendingDraft.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def discard_draft(session: AsyncSession, user_id: int) -> None:
    draft = await get_open_draft(session, user_id)
    if draft is not None:
        await session.delete(draft)
        await session.flush()


async def get_last_entry(
    session: AsyncSession, user_id: int
) -> tuple[str, FoodEntry | ActivityEntry | WeightEntry] | None:
    """Most recent non-deleted entry of any type, for /annulla and reply-less corrections."""
    candidates: list[tuple[str, FoodEntry | ActivityEntry | WeightEntry]] = []

    for kind, model, order_col in (
        ("food", FoodEntry, FoodEntry.created_at),
        ("activity", ActivityEntry, ActivityEntry.created_at),
        ("weight", WeightEntry, WeightEntry.recorded_at),
    ):
        result = await session.execute(
            select(model)
            .where(model.user_id == user_id, model.deleted_at.is_(None))
            .order_by(order_col.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            candidates.append((kind, row))

    if not candidates:
        return None

    def sort_key(item: tuple[str, FoodEntry | ActivityEntry | WeightEntry]) -> dt.datetime:
        _, entry = item
        ts = getattr(entry, "created_at", None) or entry.recorded_at
        return ts

    return max(candidates, key=sort_key)


async def soft_delete_entry(session: AsyncSession, kind: str, entry_id: int) -> bool:
    """Returns False if the entry does not exist or is already deleted."""
    model = {"food": FoodEntry, "activity": ActivityEntry, "weight": WeightEntry}[kind]
    result = await session.execute(select(model).where(model.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.deleted_at is not None:
        return False
    entry.deleted_at = utcnow()
    await session.flush()
    return True


async def get_entries_in_range(
    session: AsyncSession, kind: str, user_id: int, start: dt.datetime, end: dt.datetime
) -> list[FoodEntry] | list[ActivityEntry] | list[WeightEntry]:
    model, time_col = {
        "food": (FoodEntry, FoodEntry.consumed_at),
        "activity": (ActivityEntry, ActivityEntry.performed_at),
    }[kind]
    result = await session.execute(
        select(model)
        .where(
            model.user_id == user_id,
            model.deleted_at.is_(None),
            time_col >= start,
            time_col < end,
        )
        .order_by(time_col)
    )
    return list(result.scalars().all())


async def get_weight_entries_in_range(
    session: AsyncSession, user_id: int, start_day: dt.date, end_day: dt.date
) -> list[WeightEntry]:
    result = await session.execute(
        select(WeightEntry)
        .where(
            WeightEntry.user_id == user_id,
            WeightEntry.deleted_at.is_(None),
            WeightEntry.day >= start_day,
            WeightEntry.day < end_day,
        )
        .order_by(WeightEntry.day)
    )
    return list(result.scalars().all())


async def get_latest_weight(session: AsyncSession, user_id: int) -> WeightEntry | None:
    result = await session.execute(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id, WeightEntry.deleted_at.is_(None))
        .order_by(WeightEntry.day.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_weight_on_day(
    session: AsyncSession, user_id: int, day: dt.date
) -> WeightEntry | None:
    result = await session.execute(
        select(WeightEntry).where(
            WeightEntry.user_id == user_id,
            WeightEntry.deleted_at.is_(None),
            WeightEntry.day == day,
        )
    )
    return result.scalar_one_or_none()


async def get_current_activity_level(
    session: AsyncSession, user_id: int
) -> ActivityLevelHistory | None:
    result = await session.execute(
        select(ActivityLevelHistory)
        .where(ActivityLevelHistory.user_id == user_id)
        .order_by(ActivityLevelHistory.effective_from.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_advice_record(
    session: AsyncSession,
    user_id: int,
    surface: AdviceSurface,
    category: str,
    content: str,
    situation: str,
    topic: AdviceTopic | None,
) -> AdviceRecord:
    record = AdviceRecord(
        user_id=user_id,
        surface=surface,
        category=category,
        content=content,
        situation=situation,
        topic=topic,
    )
    session.add(record)
    await session.flush()
    return record


async def get_recent_advice_records(
    session: AsyncSession, user_id: int, limit: int = 20
) -> list[AdviceRecord]:
    result = await session.execute(
        select(AdviceRecord)
        .where(AdviceRecord.user_id == user_id, AdviceRecord.deleted_at.is_(None))
        .order_by(AdviceRecord.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_latest_advice_by_category(
    session: AsyncSession, user_id: int, category: str
) -> AdviceRecord | None:
    result = await session.execute(
        select(AdviceRecord)
        .where(
            AdviceRecord.user_id == user_id,
            AdviceRecord.deleted_at.is_(None),
            AdviceRecord.category == category,
        )
        .order_by(AdviceRecord.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_undetermined_advice_by_topic(
    session: AsyncSession, user_id: int, topic: AdviceTopic
) -> list[AdviceRecord]:
    result = await session.execute(
        select(AdviceRecord).where(
            AdviceRecord.user_id == user_id,
            AdviceRecord.deleted_at.is_(None),
            AdviceRecord.topic == topic,
            AdviceRecord.outcome == AdviceOutcome.undetermined,
        )
    )
    return list(result.scalars().all())


async def set_advice_outcome(session: AsyncSession, record: AdviceRecord, outcome: AdviceOutcome) -> None:
    record.outcome = outcome
    await session.flush()


async def get_nudge_eligible_users(session: AsyncSession) -> list[User]:
    """Non-deleted users who have opted into proactive nudges (specs/proactive-
    nudges - Nudges are off until a user opts in)."""
    result = await session.execute(
        select(User).where(User.deleted_at.is_(None), User.nudges_enabled.is_(True))
    )
    return list(result.scalars().all())


async def hard_delete_user(session: AsyncSession, user_id: int) -> None:
    """The one place soft-deletion does not apply (design.md - Safety)."""
    for model in (FoodEntry, ActivityEntry, WeightEntry, ActivityLevelHistory, PendingDraft, AdviceRecord):
        rows = (
            await session.execute(select(model).where(model.user_id == user_id))
        ).scalars().all()
        for row in rows:
            await session.delete(row)
    user = await session.get(User, user_id)
    if user is not None:
        await session.delete(user)
    await session.flush()
