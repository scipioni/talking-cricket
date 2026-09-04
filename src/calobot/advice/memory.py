"""Advice memory: recording, outcome resolution and repetition suppression. See
specs/advice-memory in full, and design.md there for why classification happens once
at write time and outcome resolution happens lazily on read rather than on a
schedule (no `background-scheduler` exists yet).
"""

from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import AdviceOutcome, AdviceRecord, AdviceSurface, AdviceTopic, User
from calobot.persistence.repository import (
    create_advice_record,
    get_latest_advice_by_category,
    get_recent_advice_records,
    get_undetermined_advice_by_topic,
    set_advice_outcome,
)
from calobot.persistence.timeutil import start_of_day_utc, today_in_timezone
from calobot.reporting.aggregation import logging_consistency_signal_for_range, meal_timing_signal_for_range

# How long the after-advice window is before an outcome is attempted, and how long
# the before-advice window compared against it is - one week each, matching how the
# underlying signals already think in weekly terms (design.md - Decisions).
OUTCOME_WINDOW_DAYS = 7

# Below these margins a change is not considered meaningful enough to call "followed"
# - see design.md - Risks: a heuristic, not derived from data, but easy to name and
# to revisit.
MEAL_TIMING_EPSILON_HOURS = 0.25
LOGGING_CONSISTENCY_EPSILON = 0.05

_MEAL_TIMING_PATTERN = re.compile(
    r"orari?\s+de[il]\s+past|mangi(?:a|are)[^.]{0,20}prima|cena[^.]{0,20}(?:presto|prima)|"
    r"tardi\s+la\s+sera|fame\s+nottur|pasti\s+serali|prima\s+di\s+(?:andare\s+a\s+)?letto",
    re.IGNORECASE,
)
_LOGGING_CONSISTENCY_PATTERN = re.compile(
    r"registra(?:re|zione)?|traccia(?:re)?|tieni\s+traccia|annota(?:re)?|logga(?:re)?|"
    r"costanza\s+nel\s+registrare",
    re.IGNORECASE,
)


def classify_topic(text: str) -> AdviceTopic | None:
    """Deterministic keyword classification of already-produced advice text, run
    once at write time (design.md - Decisions: this is code establishing a fact
    about stored text, not the model reporting on itself). A miss just means the
    record never enters outcome resolution - a weaker signal, never a wrong one."""
    if _MEAL_TIMING_PATTERN.search(text):
        return AdviceTopic.meal_timing
    if _LOGGING_CONSISTENCY_PATTERN.search(text):
        return AdviceTopic.logging_consistency
    return None


async def record_advice(
    session: AsyncSession,
    user: User,
    surface: AdviceSurface,
    category: str,
    content: str,
    situation: str,
) -> AdviceRecord:
    """Writes one advice record. No no-retention check is needed here: every write
    through the request-scoped session is already discarded on commit when
    no-retention mode is active (`NonRetentiveAsyncSession.commit`)."""
    topic = classify_topic(content)
    return await create_advice_record(session, user.id, surface, category, content, situation, topic)


async def previous_unresolved_tip(session: AsyncSession, user: User, category: str) -> str | None:
    """The most recent advice of `category` if it's still undetermined, for the
    "don't repeat this verbatim" prompt instruction. Returns None once the prior tip
    has a determined outcome, or if there isn't one yet."""
    record = await get_latest_advice_by_category(session, user.id, category)
    if record is None or record.outcome != AdviceOutcome.undetermined:
        return None
    return record.content


async def _resolve_topic(
    session: AsyncSession, user: User, tz: ZoneInfo, topic: AdviceTopic, today: dt.date
) -> None:
    signal_for_range = (
        meal_timing_signal_for_range if topic is AdviceTopic.meal_timing else logging_consistency_signal_for_range
    )
    epsilon = MEAL_TIMING_EPSILON_HOURS if topic is AdviceTopic.meal_timing else LOGGING_CONSISTENCY_EPSILON

    for record in await get_undetermined_advice_by_topic(session, user.id, topic):
        advice_day = record.created_at.astimezone(tz).date()
        after_end_day = advice_day + dt.timedelta(days=OUTCOME_WINDOW_DAYS)
        if today < after_end_day:
            continue  # not enough time has passed since the advice was given

        before_start = start_of_day_utc(advice_day - dt.timedelta(days=OUTCOME_WINDOW_DAYS), tz)
        before_end = start_of_day_utc(advice_day, tz)
        after_start = before_end
        after_end = start_of_day_utc(after_end_day, tz)

        before_value = await signal_for_range(session, user.id, before_start, before_end, tz)
        after_value = await signal_for_range(session, user.id, after_start, after_end, tz)
        if before_value is None or after_value is None:
            continue  # one of the two windows still doesn't have enough data

        if topic is AdviceTopic.meal_timing:
            # A lower typical hour means eating earlier - every timing tip this
            # codebase produces nudges in that direction (design.md - Decisions).
            improved = after_value < before_value - epsilon
        else:
            improved = after_value > before_value + epsilon

        outcome = AdviceOutcome.followed if improved else AdviceOutcome.not_followed
        await set_advice_outcome(session, record, outcome)


async def resolve_pending_outcomes(session: AsyncSession, user: User, tz: ZoneInfo) -> None:
    """Walks undetermined, topic-tagged records old enough for an after-window to
    exist yet, and settles whichever ones now have enough data on both sides. Called
    lazily wherever advice records are read, since no scheduler exists yet to sweep
    this periodically (design.md - Decisions)."""
    today = today_in_timezone(tz)
    await _resolve_topic(session, user, tz, AdviceTopic.meal_timing, today)
    await _resolve_topic(session, user, tz, AdviceTopic.logging_consistency, today)


async def advice_history(session: AsyncSession, user: User, tz: ZoneInfo, limit: int = 20) -> list[AdviceRecord]:
    """Resolves what can now be resolved, then returns recent records - the payload
    behind `get_advice_history` in `calobot.advice.tools`."""
    await resolve_pending_outcomes(session, user, tz)
    return await get_recent_advice_records(session, user.id, limit)
