"""Weight entry lifecycle: normalization -> plausibility -> one-per-day storage.
See specs/weight-logging in full."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import User, WeightEntry
from calobot.persistence.repository import get_latest_weight, get_weight_on_day
from calobot.persistence.timeutil import today_in_timezone, utcnow
from calobot.weight.normalizer import WeightNormalization

MIN_PLAUSIBLE_KG = 30
MAX_PLAUSIBLE_KG = 400
# Beyond this many kg/day of implied change, ask for confirmation rather than storing
# silently (specs/weight-logging - Implausible jump). Generous on purpose: it should
# only catch near-certain misreadings, not fast but real short-term water-weight swings.
MAX_PLAUSIBLE_KG_PER_DAY = 1.0


@dataclass(frozen=True)
class Rejected:
    reason: Literal["out_of_range", "no_previous_weight"]


@dataclass(frozen=True)
class NeedsConfirmation:
    proposed_kg: float
    day: dt.date


@dataclass(frozen=True)
class Stored:
    entry: WeightEntry
    replaced_previous: bool
    goal_reached: bool


WeightApplyResult = Rejected | NeedsConfirmation | Stored


def resolve_day(when_text: str | None, tz, today: dt.date | None = None) -> dt.date:
    today = today or today_in_timezone(tz)
    if when_text and "ieri" in when_text.lower():
        return today - dt.timedelta(days=1)
    return today


async def resolve_target_kg(
    session: AsyncSession, user_id: int, normalization: WeightNormalization
) -> float | Literal["no_previous_weight"] | None:
    if normalization.kg_absolute is not None:
        return normalization.kg_absolute

    if normalization.delta_kg is not None and normalization.direction is not None:
        last = await get_latest_weight(session, user_id)
        if last is None:
            return "no_previous_weight"
        sign = 1 if normalization.direction == "gain" else -1
        return last.kg + sign * normalization.delta_kg

    return None


async def apply_weight(
    session: AsyncSession,
    user: User,
    normalization: WeightNormalization,
    when_text: str | None,
    tz,
    *,
    confirmed: bool = False,
) -> WeightApplyResult:
    target_kg = await resolve_target_kg(session, user.id, normalization)
    if target_kg == "no_previous_weight":
        return Rejected(reason="no_previous_weight")
    if target_kg is None:
        return Rejected(reason="out_of_range")  # extraction gave us nothing usable

    if not (MIN_PLAUSIBLE_KG <= target_kg <= MAX_PLAUSIBLE_KG):
        return Rejected(reason="out_of_range")

    day = resolve_day(when_text, tz)
    previous = await get_latest_weight(session, user.id)

    if not confirmed and previous is not None:
        days_elapsed = max(abs((day - previous.day).days), 1)
        if abs(target_kg - previous.kg) / days_elapsed > MAX_PLAUSIBLE_KG_PER_DAY:
            return NeedsConfirmation(proposed_kg=target_kg, day=day)

    existing = await get_weight_on_day(session, user.id, day)
    replaced = existing is not None
    if existing is not None:
        existing.kg = target_kg
        existing.recorded_at = utcnow()
        entry = existing
    else:
        entry = WeightEntry(user_id=user.id, kg=target_kg, day=day)
        session.add(entry)
    await session.flush()

    goal_reached = _goal_reached(
        previous_kg=previous.kg if previous else None,
        target_kg=target_kg,
        goal_kg=user.peso_obiettivo_kg,
    )

    return Stored(entry=entry, replaced_previous=replaced, goal_reached=goal_reached)


def _goal_reached(*, previous_kg: float | None, target_kg: float, goal_kg: float | None) -> bool:
    if goal_kg is None:
        return False
    if abs(target_kg - goal_kg) < 0.1:
        return True
    if previous_kg is None:
        return False
    was_above_goal = previous_kg > goal_kg
    return (was_above_goal and target_kg <= goal_kg) or (
        not was_above_goal and target_kg >= goal_kg
    )
