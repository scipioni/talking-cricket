"""Fuzzy candidate retrieval (tasks.md 3.5). Retrieval is deliberately cheap and can be
sloppy: the language model disambiguates among candidates, so recall matters more than
precision here (design.md - Calorie resolution: 'the model as a matcher, not a search engine')."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import FoodDataRow, METDataRow

MAX_CANDIDATES = 8


@dataclass(frozen=True)
class FoodCandidate:
    id: int
    source_name_en: str
    kcal_per_100g: float
    protein_per_100g: float | None
    fat_per_100g: float | None
    carbs_per_100g: float | None
    fiber_per_100g: float | None
    matched_alias: str
    # Reference portions (specs/food-logging - Quantity resolution): null on rows
    # where no portion question makes sense.
    portion_small_g: float | None = None
    portion_medium_g: float | None = None
    portion_generous_g: float | None = None


@dataclass(frozen=True)
class METCandidate:
    id: int
    name_it: str
    intensity: str | None
    met: float


async def retrieve_food_candidates(session: AsyncSession, query: str) -> list[FoodCandidate]:
    rows = (await session.execute(select(FoodDataRow))).scalars().all()

    # Expand each row into (alias, row) pairs so the match score is against a single alias,
    # not a semicolon-joined blob.
    alias_pairs: list[tuple[str, FoodDataRow]] = []
    for row in rows:
        for alias in row.aliases_it.split(";"):
            alias = alias.strip()
            if alias:
                alias_pairs.append((alias, row))

    if not alias_pairs:
        return []

    aliases = [alias for alias, _ in alias_pairs]
    matches = process.extract(
        query, aliases, scorer=fuzz.WRatio, limit=MAX_CANDIDATES * 3
    )

    seen_row_ids: set[int] = set()
    candidates: list[FoodCandidate] = []
    for matched_alias, _score, idx in matches:
        row = alias_pairs[idx][1]
        if row.id in seen_row_ids:
            continue
        seen_row_ids.add(row.id)
        candidates.append(
            FoodCandidate(
                id=row.id,
                source_name_en=row.source_name_en,
                kcal_per_100g=row.kcal_per_100g,
                protein_per_100g=row.protein_per_100g,
                fat_per_100g=row.fat_per_100g,
                carbs_per_100g=row.carbs_per_100g,
                fiber_per_100g=row.fiber_per_100g,
                matched_alias=matched_alias,
                portion_small_g=row.portion_small_g,
                portion_medium_g=row.portion_medium_g,
                portion_generous_g=row.portion_generous_g,
            )
        )
        if len(candidates) >= MAX_CANDIDATES:
            break

    return candidates


async def table_portions_for(
    session: AsyncSession, description: str
) -> tuple[float, float, float] | None:
    """The bundled table's reference portions for a described food, or None
    (specs/food-logging - Quantity resolution: the table's scale comes before the
    extraction's guesses). The first retrieved candidate with a complete triple
    wins; retrieval is the same fuzzy pass the calorie path uses, but held to a
    similarity floor: retrieval itself has none (the calorie path can afford that
    because the model disambiguates), and without one every query matches
    something - 'sushi' would offer a plum's portions. 80 keeps exact and
    inflected matches (cipolla 100, 'cipolla cotta' 90) and rejects the rest."""
    from rapidfuzz import fuzz

    rows = (await session.execute(select(FoodDataRow))).scalars().all()
    alias_pairs: list[tuple[str, FoodDataRow]] = []
    for row in rows:
        for alias in row.aliases_it.split(";"):
            alias = alias.strip()
            if alias:
                alias_pairs.append((alias, row))

    if not alias_pairs:
        return None

    best: FoodDataRow | None = None
    best_score = 0.0
    for alias, row in alias_pairs:
        score = fuzz.WRatio(description.strip().lower(), alias)
        if score > best_score:
            best, best_score = row, score
    if best is None or best_score < 80:
        return None
    if (
        best.portion_small_g is not None
        and best.portion_medium_g is not None
        and best.portion_generous_g is not None
    ):
        return (best.portion_small_g, best.portion_medium_g, best.portion_generous_g)
    return None


async def retrieve_met_candidates(session: AsyncSession, query: str) -> list[METCandidate]:
    rows = (await session.execute(select(METDataRow))).scalars().all()
    if not rows:
        return []

    names = [row.name_it for row in rows]
    matches = process.extract(query, names, scorer=fuzz.WRatio, limit=MAX_CANDIDATES)

    candidates = []
    for _matched_name, _score, idx in matches:
        row = rows[idx]
        candidates.append(
            METCandidate(id=row.id, name_it=row.name_it, intensity=row.intensity, met=row.met)
        )
    return candidates
