"""Scoring by comparison, not by reading (specs/conversation-simulation - Scoring by
comparison, not by reading).

Each step declares what it means and what should follow. The oracle diffs the
database before and after the step and checks the replies, producing a verdict with
no human in the loop. What a step *said* is recorded for the report but never used
to decide whether it passed - the intent is the contract, the words are incidental.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import FoodEntry, WeightEntry
from calobot.persistence.timeutil import day_in_timezone

from .scenario import (
    AskedAgain,
    DeclinedAndRedirected,
    Expectation,
    NothingStored,
    Step,
    StoredFood,
    StoredWeight,
)
from .transport import SentMessage

# Words that mark a redirection to a professional. Checked as a set of markers rather
# than as a phrase, because the wording is the model's to choose.
_REDIRECTION_MARKERS = (
    "professionista",
    "medico",
    "nutrizionista",
    "dietologo",
    "dietista",
)


@dataclass(frozen=True)
class Snapshot:
    food_ids: frozenset[int]
    # Weight is one row per local day, so logging a weight often *updates* a row
    # rather than inserting one - onboarding already wrote today's. Ids alone would
    # show no change, so the values are captured too.
    weight_by_day: dict[object, float]


@dataclass(frozen=True)
class Verdict:
    step_index: int
    passed: bool
    expected: str
    detail: str
    intent: str
    said: str
    replies: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        mark = "ok" if self.passed else "FAIL"
        return f"[{mark}] step {self.step_index}: expected {self.expected}; {self.detail}"


async def snapshot(session: AsyncSession, user_id: int) -> Snapshot:
    session.expire_all()
    food = await session.execute(
        select(FoodEntry.id).where(FoodEntry.user_id == user_id, FoodEntry.deleted_at.is_(None))
    )
    weight = await session.execute(
        select(WeightEntry.day, WeightEntry.kg).where(
            WeightEntry.user_id == user_id, WeightEntry.deleted_at.is_(None)
        )
    )
    return Snapshot(frozenset(food.scalars()), {day: kg for day, kg in weight})


async def _new_food(
    session: AsyncSession, before: Snapshot, after: Snapshot
) -> list[FoodEntry]:
    added = after.food_ids - before.food_ids
    if not added:
        return []
    result = await session.execute(select(FoodEntry).where(FoodEntry.id.in_(added)))
    return list(result.scalars())


def _weight_changes(before: Snapshot, after: Snapshot) -> dict[object, float]:
    """Days whose recorded weight was added or altered. An update counts as a change:
    from the user's side, replacing today's 90 kg with 89.5 kg is a weight being
    logged, not a no-op."""
    return {
        day: kg for day, kg in after.weight_by_day.items() if before.weight_by_day.get(day) != kg
    }


def _asks_something(replies: list[SentMessage]) -> bool:
    if any(reply.options for reply in replies):
        return True
    return any("?" in reply.text for reply in replies)


def _redirects(replies: list[SentMessage]) -> bool:
    joined = " ".join(reply.text.lower() for reply in replies)
    return any(marker in joined for marker in _REDIRECTION_MARKERS)


async def score(
    session: AsyncSession,
    user_id: int,
    tz: ZoneInfo,
    *,
    step_index: int,
    step: Step,
    said: str,
    replies: list[SentMessage],
    before: Snapshot,
    after: Snapshot,
) -> Verdict:
    expectation: Expectation = step.expect
    new_food = await _new_food(session, before, after)
    weight_changes = _weight_changes(before, after)
    stored_anything = bool(new_food or weight_changes)

    def verdict(passed: bool, detail: str) -> Verdict:
        return Verdict(
            step_index=step_index,
            passed=passed,
            expected=expectation.describe(),
            detail=detail,
            intent=step.intent,
            said=said,
            replies=[reply.text for reply in replies],
        )

    if isinstance(expectation, NothingStored):
        if stored_anything:
            return verdict(
                False, f"but {len(new_food)} food and {len(weight_changes)} weight entries changed"
            )
        return verdict(True, "nothing was stored")

    if isinstance(expectation, AskedAgain):
        if stored_anything:
            return verdict(False, "but an entry was stored instead of a question being asked")
        if not _asks_something(replies):
            return verdict(False, f"but the bot did not ask anything: {[r.text for r in replies]}")
        return verdict(True, "the bot asked again and stored nothing")

    if isinstance(expectation, DeclinedAndRedirected):
        if stored_anything:
            return verdict(False, "but an entry was stored")
        if not _redirects(replies):
            return verdict(
                False,
                "but the reply does not point the user at a professional: "
                f"{[r.text for r in replies]}",
            )
        return verdict(True, "the bot declined and redirected")

    if isinstance(expectation, StoredFood):
        if len(new_food) != 1:
            return verdict(False, f"but {len(new_food)} food entries were stored")
        entry = new_food[0]
        if expectation.description_contains.lower() not in entry.description.lower():
            return verdict(False, f"but the entry stored was {entry.description!r}")
        allowed = expectation.grams * expectation.tolerance
        if abs(entry.grams - expectation.grams) > allowed:
            return verdict(
                False,
                f"but the entry stored {entry.grams:.0f} g, outside "
                f"{expectation.grams:.0f} g +/- {allowed:.0f} g",
            )
        if expectation.on_local_day is not None:
            actual_day = day_in_timezone(entry.consumed_at, tz)
            if actual_day != expectation.on_local_day:
                return verdict(
                    False, f"but the entry landed on {actual_day}, not {expectation.on_local_day}"
                )
        return verdict(True, f"stored {entry.description!r} {entry.grams:.0f} g")

    if isinstance(expectation, StoredWeight):
        if len(weight_changes) != 1:
            return verdict(
                False, f"but {len(weight_changes)} days' weights changed, expected exactly one"
            )
        day, kg = next(iter(weight_changes.items()))
        if abs(kg - expectation.kg) > expectation.tolerance_kg:
            return verdict(False, f"but the weight recorded for {day} is {kg:.1f} kg")
        return verdict(True, f"recorded {kg:.1f} kg for {day}")

    raise TypeError(f"unhandled expectation: {expectation!r}")
