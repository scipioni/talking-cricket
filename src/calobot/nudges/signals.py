"""The three earned signals a nudge may be sent for. See design.md - Decisions for
why each has the shape it does (prior-engagement requirement for the broken streak,
recency window for goal-reached, age filter for the unresolved suggestion) and for
the fixed priority order `find_candidate` applies.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import AdviceRecord, AdviceTopic, User
from calobot.persistence.repository import (
    get_entries_in_range,
    get_latest_weight,
    get_undetermined_advice_by_topic,
)
from calobot.persistence.timeutil import start_of_day_utc, today_in_timezone
from calobot.settings import Settings

# Within this margin of the goal weight counts as "reached" - looser than the
# budget's own maintenance-mode threshold (0.1kg in profile/budget.py), since that
# threshold decides a computed number while this only decides whether to say
# something.
GOAL_REACHED_TOLERANCE_KG = 0.5

NudgeKind = Literal["goal_reached", "broken_streak", "unresolved_suggestion"]


@dataclass(frozen=True)
class NudgeCandidate:
    kind: NudgeKind
    advice_record: AdviceRecord | None = None


async def goal_reached_recently(session: AsyncSession, user: User, tz: ZoneInfo, settings: Settings) -> bool:
    if user.peso_obiettivo_kg is None:
        return False
    latest = await get_latest_weight(session, user.id)
    if latest is None:
        return False
    if abs(latest.kg - user.peso_obiettivo_kg) > GOAL_REACHED_TOLERANCE_KG:
        return False
    today = today_in_timezone(tz)
    return (today - latest.day).days <= settings.nudge_goal_reached_recency_days


async def broken_logging_streak(session: AsyncSession, user: User, tz: ZoneInfo, settings: Settings) -> bool:
    today = today_in_timezone(tz)
    gap_start = start_of_day_utc(today - dt.timedelta(days=settings.nudge_streak_break_days), tz)
    gap_end = start_of_day_utc(today + dt.timedelta(days=1), tz)
    recent_entries = await get_entries_in_range(session, "food", user.id, gap_start, gap_end)
    if recent_entries:
        return False  # no gap at all

    prior_start = start_of_day_utc(
        today - dt.timedelta(days=settings.nudge_streak_break_days + 30), tz
    )
    prior_entries = await get_entries_in_range(session, "food", user.id, prior_start, gap_start)
    return len(prior_entries) > 0  # only a *break* if there was something to break


async def unresolved_suggestion(
    session: AsyncSession, user: User, tz: ZoneInfo, settings: Settings
) -> AdviceRecord | None:
    today = today_in_timezone(tz)
    candidates: list[AdviceRecord] = []
    for topic in (AdviceTopic.meal_timing, AdviceTopic.logging_consistency):
        candidates.extend(await get_undetermined_advice_by_topic(session, user.id, topic))

    old_enough = [
        r
        for r in candidates
        if (today - r.created_at.astimezone(tz).date()).days >= settings.nudge_suggestion_min_age_days
    ]
    if not old_enough:
        return None
    return min(old_enough, key=lambda r: r.created_at)


async def find_candidate(
    session: AsyncSession, user: User, tz: ZoneInfo, settings: Settings
) -> NudgeCandidate | None:
    """Fixed priority: goal-reached, then broken-streak, then unresolved-suggestion
    (design.md - Decisions). At most one candidate is ever returned."""
    if await goal_reached_recently(session, user, tz, settings):
        return NudgeCandidate(kind="goal_reached")
    if await broken_logging_streak(session, user, tz, settings):
        return NudgeCandidate(kind="broken_streak")
    record = await unresolved_suggestion(session, user, tz, settings)
    if record is not None:
        return NudgeCandidate(kind="unresolved_suggestion", advice_record=record)
    return None
