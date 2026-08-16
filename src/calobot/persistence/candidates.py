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
    matched_alias: str


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
                matched_alias=matched_alias,
            )
        )
        if len(candidates) >= MAX_CANDIDATES:
            break

    return candidates


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
