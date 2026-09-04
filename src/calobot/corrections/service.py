"""Undo, amend and delete. See specs/entry-correction in full.

Targeting is deterministic: by /annulla (most recent entry), by a confirmation
message's inline controls (callback_data carries kind+id directly), or by replying
to a confirmation message (confirmation_message_id -> entry lookup). Free-text
references to older, untargeted entries are explicitly refused (design.md -
'the Telegram trick that collapses most of the difficulty')."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import ActivityEntry, FoodEntry, WeightEntry
from calobot.persistence.repository import get_last_entry, soft_delete_entry

EntryKind = Literal["food", "activity", "weight"]

_MODEL_BY_KIND: dict[EntryKind, type[FoodEntry] | type[ActivityEntry] | type[WeightEntry]] = {
    "food": FoodEntry,
    "activity": ActivityEntry,
    "weight": WeightEntry,
}


@dataclass(frozen=True)
class NoEntry:
    pass


@dataclass(frozen=True)
class AlreadyDeleted:
    pass


@dataclass(frozen=True)
class Deleted:
    kind: EntryKind
    entry_id: int


UndoResult = NoEntry | Deleted


async def undo_last(session: AsyncSession, user_id: int) -> UndoResult:
    last = await get_last_entry(session, user_id)
    if last is None:
        return NoEntry()
    kind, entry = last
    ok = await soft_delete_entry(session, kind, entry.id)
    if not ok:
        return NoEntry()
    return Deleted(kind=kind, entry_id=entry.id)


async def delete_by_target(session: AsyncSession, kind: EntryKind, entry_id: int) -> UndoResult:
    model = _MODEL_BY_KIND[kind]
    existing = (
        await session.execute(select(model).where(model.id == entry_id))
    ).scalar_one_or_none()
    if existing is None:
        return NoEntry()
    if existing.deleted_at is not None:
        return AlreadyDeleted()
    await soft_delete_entry(session, kind, entry_id)
    return Deleted(kind=kind, entry_id=entry_id)


async def find_entry_by_confirmation_message(
    session: AsyncSession, message_id: int
) -> tuple[EntryKind, FoodEntry | ActivityEntry | WeightEntry] | None:
    for kind, model in _MODEL_BY_KIND.items():
        result = await session.execute(
            select(model).where(
                model.confirmation_message_id == message_id, model.deleted_at.is_(None)
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return kind, row
    return None


async def set_confirmation_message_id(
    session: AsyncSession, kind: EntryKind, entry_id: int, message_id: int
) -> None:
    model = _MODEL_BY_KIND[kind]
    entry = await session.get(model, entry_id)
    if entry is not None:
        entry.confirmation_message_id = message_id
        await session.flush()


@dataclass(frozen=True)
class FoodAmendment:
    quantity_grams: float | None = None
    description: str | None = None


async def amend_food_quantity(
    session: AsyncSession, entry: FoodEntry, new_grams: float
) -> FoodEntry:
    """Recomputes kcal from the entry's existing kcal_per_100g - correcting only the
    quantity does not require re-resolving energy (specs/entry-correction -
    Correcting a quantity). Macro grams are rescaled by the same grams ratio, since
    the entry has no separately stored per-100g macro rate to recompute from
    directly (specs/food-logging - Food entry macro-nutrient contents: a doubled
    portion doubles macros consistently with kcal)."""
    old_grams = entry.grams
    ratio = new_grams / old_grams if old_grams else None

    def rescale(grams_value: float | None) -> float | None:
        if grams_value is None or ratio is None:
            return grams_value
        return grams_value * ratio

    entry.protein_g = rescale(entry.protein_g)
    entry.fat_g = rescale(entry.fat_g)
    entry.carbs_g = rescale(entry.carbs_g)
    entry.fiber_g = rescale(entry.fiber_g)
    entry.grams = new_grams
    entry.kcal = entry.kcal_per_100g * new_grams / 100.0
    await session.flush()
    return entry
