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


async def seed_food_data(session: AsyncSession) -> int:
    existing = (await session.execute(select(FoodDataRow.source_name_en))).scalars().all()
    existing_names = set(existing)

    inserted = 0
    for row in _read_csv("food_data.csv"):
        if row["source_name_en"] in existing_names:
            continue
        session.add(
            FoodDataRow(
                source_name_en=row["source_name_en"],
                kcal_per_100g=float(row["kcal_per_100g"]),
                aliases_it=row["aliases_it"],
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
