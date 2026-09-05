"""The nudge cycle itself: iterate opted-in users, apply the rate limit and quiet
hours, evaluate signals, compose and send. Registered as the one scheduler job this
change adds - see design.md - Decisions for why it lives here rather than inside
`calobot.scheduler` (which stays generic) or as an LLM-composed message (it isn't
one, by design)."""

from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.nudges.messages import compose
from calobot.nudges.signals import find_candidate
from calobot.persistence.engine import get_session_factory
from calobot.persistence.models import User
from calobot.persistence.repository import get_nudge_eligible_users
from calobot.persistence.timeutil import utcnow
from calobot.safety.medical import is_medical_topic
from calobot.settings import Settings
from calobot.telegram.keyboards import nudge_stop_keyboard

logger = logging.getLogger(__name__)


def _in_quiet_hours(now_local: dt.datetime, settings: Settings) -> bool:
    hour = now_local.hour
    start, end = settings.nudge_quiet_hours_start, settings.nudge_quiet_hours_end
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps past midnight


def _aware(moment: dt.datetime) -> dt.datetime:
    """SQLite returns naive datetimes even from timezone-aware columns; every read
    path in the system treats a naive stored instant as UTC. Without this, the first
    stored send makes the next cycle's subtraction raise TypeError - found by the
    time-lapse harness, which is the first thing to run the cycle twice after a
    send (openspec/changes/time-lapse-simulation)."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=dt.UTC)


def _rate_limited(user: User, now: dt.datetime, settings: Settings) -> bool:
    if user.last_nudge_sent_at is None:
        return False
    elapsed = now - _aware(user.last_nudge_sent_at)
    return elapsed < dt.timedelta(days=settings.nudge_min_interval_days)


async def _maybe_nudge_user(
    bot: Bot, session: AsyncSession, user: User, tz: ZoneInfo, settings: Settings
) -> None:
    from calobot.telemetry.context import no_retention_chats

    if user.telegram_user_id in no_retention_chats:
        return  # specs/proactive-nudges - No-retention mode suppresses nudges entirely

    now = utcnow()
    if _rate_limited(user, now, settings):
        return
    if _in_quiet_hours(now.astimezone(tz), settings):
        return

    candidate = await find_candidate(session, user, tz, settings)
    if candidate is None:
        return

    text = compose(candidate)
    if is_medical_topic(text):
        # Defense-in-depth only (design.md - Risks): a fixed template should never
        # trip this, but a nudge that somehow does is not sent.
        logger.warning("suppressed a nudge that tripped the medical-topic check")
        return

    await bot.send_message(user.telegram_user_id, text, reply_markup=nudge_stop_keyboard())
    user.last_nudge_sent_at = now
    await session.commit()


async def run_nudge_cycle(bot: Bot, settings: Settings) -> None:
    """The job registered on the scheduler. One request-scoped session for the
    whole cycle; each user's send (if any) commits independently so one user's
    outcome cannot roll back another's."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        users = await get_nudge_eligible_users(session)
        for user in users:
            await _maybe_nudge_user(bot, session, user, settings.timezone, settings)
