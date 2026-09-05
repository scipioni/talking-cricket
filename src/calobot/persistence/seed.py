"""Idempotent seeding of the bundled food and MET tables at startup (tasks.md 3.4).
Keyed by natural content so re-running never duplicates rows: existing rows are
left untouched, only missing ones are inserted."""

from __future__ import annotations

import csv
from importlib import resources

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import FoodDataRow, METDataRow


def _read_csv(filename: str) -> list[dict[str, str]]:
    with resources.files("calobot.data").joinpath(filename).open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _optional_float(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "")
    return float(value) if value else None


async def seed_food_data(session: AsyncSession) -> int:
    existing_rows = (await session.execute(select(FoodDataRow))).scalars().all()
    existing_by_name = {row.source_name_en: row for row in existing_rows}

    inserted = 0
    for row in _read_csv("food_data.csv"):
        existing = existing_by_name.get(row["source_name_en"])
        if existing is not None:
            # A row seeded before the macro columns existed (add-macro-nutrient-tracking)
            # would otherwise stay null forever, since this loop only inserts missing
            # rows - backfill its macro columns from the CSV if they're still unset.
            if existing.protein_per_100g is None:
                existing.protein_per_100g = _optional_float(row, "protein_per_100g")
            if existing.fat_per_100g is None:
                existing.fat_per_100g = _optional_float(row, "fat_per_100g")
            if existing.carbs_per_100g is None:
                existing.carbs_per_100g = _optional_float(row, "carbs_per_100g")
            if existing.fiber_per_100g is None:
                existing.fiber_per_100g = _optional_float(row, "fiber_per_100g")
            # Same backfill for the reference portions (food-table-reference-portions):
            # a row seeded before the columns existed stays null forever otherwise.
            if existing.portion_small_g is None:
                existing.portion_small_g = _optional_float(row, "portion_small_g")
            if existing.portion_medium_g is None:
                existing.portion_medium_g = _optional_float(row, "portion_medium_g")
            if existing.portion_generous_g is None:
                existing.portion_generous_g = _optional_float(row, "portion_generous_g")
            continue
        session.add(
            FoodDataRow(
                source_name_en=row["source_name_en"],
                kcal_per_100g=float(row["kcal_per_100g"]),
                protein_per_100g=_optional_float(row, "protein_per_100g"),
                fat_per_100g=_optional_float(row, "fat_per_100g"),
                carbs_per_100g=_optional_float(row, "carbs_per_100g"),
                fiber_per_100g=_optional_float(row, "fiber_per_100g"),
                aliases_it=row["aliases_it"],
                portion_small_g=_optional_float(row, "portion_small_g"),
                portion_medium_g=_optional_float(row, "portion_medium_g"),
                portion_generous_g=_optional_float(row, "portion_generous_g"),
            )
        )
        inserted += 1
    await session.flush()
    return inserted


async def seed_met_data(session: AsyncSession) -> int:
    existing = (
        await session.execute(select(METDataRow.name_it, METDataRow.intensity))
    ).all()
    existing_keys = {(name, intensity) for name, intensity in existing}

    inserted = 0
    for row in _read_csv("met_data.csv"):
        intensity = row["intensity"] or None
        key = (row["name_it"], intensity)
        if key in existing_keys:
            continue
        session.add(
            METDataRow(
                name_it=row["name_it"],
                intensity=intensity,
                met=float(row["met"]),
                source_note=row["source_note"],
            )
        )
        inserted += 1
    await session.flush()
    return inserted


async def seed_all(session: AsyncSession) -> None:
    await seed_food_data(session)
    await seed_met_data(session)
    await session.commit()
