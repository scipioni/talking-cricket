"""Properties that must hold no matter what the user said or the model returned
(specs/conversation-simulation - Hard invariants are checked after every action).

Evaluated after every inbound action rather than at the end of a scenario. Checking
at the end tells you a database is inconsistent; checking after each action tells you
which message made it so, which is the difference between a report someone can act
on and one they have to bisect by hand.

A violation fails a run regardless of what the step itself expected: a step can be
satisfied and the database still be wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import ActivityEntry, FoodEntry, PendingDraft, WeightEntry
from calobot.persistence.timeutil import day_bounds_utc, day_in_timezone
from calobot.reporting.aggregation import build_daily_kcal_breakdown, build_food_report

# Floating point: kcal are sums of products, so exact equality would flag rounding.
TOLERANCE_KCAL = 0.01


@dataclass(frozen=True)
class Violation:
    invariant: str
    detail: str

    def __str__(self) -> str:
        return f"{self.invariant}: {self.detail}"


# A reply asserting that something was recorded, changed or removed. The negated
# forms are stripped first because the ignored-text notice ("non l'ho registrato")
# legitimately contains the same word while asserting the opposite. Deletion and
# modification stems were added alongside the production guard's for the advice
# agent (specs/advice-agent - a false claim of deletion is the same failure as a
# false claim of creation), so this independent detector keeps covering the same
# concept the production one does, even though the two remain separately
# implemented.
_NEGATED_CLAIM = re.compile(
    r"non\s+(?:l['’]ho|ho|le\s+ho|li\s+ho)\s+\w*"
    r"(?:registrat|salvat|eliminat|cancellat|modificat)\w*"
)
# A whole interrogative sentence, removed before anything else is looked at: a
# question about a record is not a claim of one. A live run flagged the correction
# path's "Intendi correggere l'ultima voce registrata o e una voce nuova?", where the
# participle describes an existing entry rather than asserting a new one.
_QUESTION = re.compile(r"[^.!?\n]*\?")
_CLAIM = re.compile(
    r"\b(?:ho\s+)?(?:registrat|salvat|memorizzat|aggiunt|eliminat|cancellat|modificat|rimoss)\w*\b"
)


def claims_something_was_recorded(text: str) -> bool:
    """Whether a reply tells the user something went into the log.

    Deliberately a different implementation from the production guard in
    `calobot/safety/claims.py` - see the note there. This one deletes the spans that
    cannot carry a claim (questions, then negated phrases) and looks at what is left;
    the production one tokenises into sentences and clauses and scopes each rule.

    They are meant to be able to disagree. Note that on the case above they did *not*:
    both flagged it, and only the guard's placement kept it out of production. Two
    implementations reduce the odds of a shared blind spot; they do not remove them.
    """
    without_questions = _QUESTION.sub("", text.lower())
    return bool(_CLAIM.search(_NEGATED_CLAIM.sub("", without_questions)))


async def _all_food(session: AsyncSession, user_id: int) -> list[FoodEntry]:
    result = await session.execute(select(FoodEntry).where(FoodEntry.user_id == user_id))
    return list(result.scalars())


async def _all_activity(session: AsyncSession, user_id: int) -> list[ActivityEntry]:
    result = await session.execute(select(ActivityEntry).where(ActivityEntry.user_id == user_id))
    return list(result.scalars())


async def _no_entry_without_a_quantity(
    session: AsyncSession, user_id: int, tz: ZoneInfo
) -> list[Violation]:
    """The one thing a photo or a vague message can never establish, and the thing the
    clarification loop exists to obtain. An entry stored without it is a silently
    wrong number in every aggregate downstream."""
    violations = []
    for entry in await _all_food(session, user_id):
        if entry.deleted_at is None and not entry.grams > 0:
            violations.append(
                Violation(
                    "entry without a quantity",
                    f"food entry {entry.id} ({entry.description!r}) has grams={entry.grams}",
                )
            )
    for activity in await _all_activity(session, user_id):
        if activity.deleted_at is None and not activity.duration_minutes > 0:
            violations.append(
                Violation(
                    "entry without a quantity",
                    f"activity entry {activity.id} ({activity.activity!r}) has "
                    f"duration_minutes={activity.duration_minutes}",
                )
            )
    return violations


async def _deleted_entries_stay_out_of_aggregates(
    session: AsyncSession, user_id: int, tz: ZoneInfo
) -> list[Violation]:
    """Soft deletion is only a deletion if every read path honours it. Checked by
    rebuilding each affected day's report and comparing it against the entries that
    should count - which also catches a day total that has simply drifted."""
    entries = await _all_food(session, user_id)
    if not entries:
        return []

    violations = []
    days = {day_in_timezone(entry.consumed_at, tz) for entry in entries}
    for day in sorted(days):
        start, end = day_bounds_utc(day, tz)
        expected = sum(
            entry.kcal
            for entry in entries
            if entry.deleted_at is None and start <= _aware(entry.consumed_at) < end
        )
        report = await build_food_report(session, user_id, "day", day, tz, None)
        actual = report.total_kcal if report.has_data else 0.0
        if abs(actual - expected) > TOLERANCE_KCAL:
            deleted_on_day = [
                entry.id
                for entry in entries
                if entry.deleted_at is not None and start <= _aware(entry.consumed_at) < end
            ]
            violations.append(
                Violation(
                    "day total disagrees with its entries",
                    f"{day}: report says {actual:.2f} kcal, non-deleted entries sum to "
                    f"{expected:.2f} kcal (deleted entries on that day: {deleted_on_day or 'none'})",
                )
            )
    return violations


async def _entries_land_on_their_own_local_day(
    session: AsyncSession, user_id: int, tz: ZoneInfo
) -> list[Violation]:
    """An entry must be counted on the local day its instant falls in, and on no
    other. This is what a timezone or day-boundary bug corrupts, and it corrupts it
    invisibly - the totals still look plausible."""
    entries = [e for e in await _all_food(session, user_id) if e.deleted_at is None]
    if not entries:
        return []

    violations = []
    days = sorted({day_in_timezone(entry.consumed_at, tz) for entry in entries})
    for day in days:
        breakdown = await build_daily_kcal_breakdown(session, user_id, "day", day, tz)
        expected = sum(
            entry.kcal for entry in entries if day_in_timezone(entry.consumed_at, tz) == day
        )
        actual = breakdown.get(day, 0.0)
        if abs(actual - expected) > TOLERANCE_KCAL:
            violations.append(
                Violation(
                    "entry counted on the wrong local day",
                    f"{day} in {tz.key}: breakdown says {actual:.2f} kcal, entries whose "
                    f"instant falls on that day sum to {expected:.2f} kcal",
                )
            )
        stray = {other for other in breakdown if other != day}
        if stray:
            violations.append(
                Violation(
                    "entry counted on the wrong local day",
                    f"the breakdown for {day} also reported {sorted(stray)}",
                )
            )
    return violations


async def _no_draft_left_without_a_question(
    session: AsyncSession, user_id: int, tz: ZoneInfo
) -> list[Violation]:
    """Between actions, an open draft is always waiting on an answer to something.
    One with no question outstanding is unreachable state: the user has no way to
    advance it and no way to know it is there."""
    result = await session.execute(select(PendingDraft).where(PendingDraft.user_id == user_id))
    violations = []
    for draft in result.scalars():
        if draft.awaiting_field is None:
            violations.append(
                Violation(
                    "draft open with no question outstanding",
                    f"draft {draft.id} (intent={draft.intent}) is waiting on nothing",
                )
            )
    return violations


async def _weight_entries_have_a_plausible_value(
    session: AsyncSession, user_id: int, tz: ZoneInfo
) -> list[Violation]:
    result = await session.execute(select(WeightEntry).where(WeightEntry.user_id == user_id))
    violations = []
    for entry in result.scalars():
        if entry.deleted_at is None and not 20 < entry.kg < 400:
            violations.append(
                Violation(
                    "implausible stored value",
                    f"weight entry {entry.id} holds {entry.kg} kg",
                )
            )
    return violations


def _aware(moment):
    """SQLite returns naive datetimes even from timezone-aware columns; every read
    path in the system treats a naive stored instant as UTC."""
    import datetime as dt

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=dt.UTC)


ALL_INVARIANTS = (
    _no_entry_without_a_quantity,
    _deleted_entries_stay_out_of_aggregates,
    _entries_land_on_their_own_local_day,
    _no_draft_left_without_a_question,
    _weight_entries_have_a_plausible_value,
)


async def check_all(session: AsyncSession, user_id: int, tz: ZoneInfo) -> list[Violation]:
    violations: list[Violation] = []
    for invariant in ALL_INVARIANTS:
        violations.extend(await invariant(session, user_id, tz))
    return violations
