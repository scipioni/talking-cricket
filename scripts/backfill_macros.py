"""One-off backfill: resolves protein/fat/carbohydrate/fiber grams for FoodEntry rows
logged before the add-macro-nutrient-tracking change. See
openspec/changes/add-macro-nutrient-tracking/design.md - Decisions.

Never touches an entry's kcal, kcal_per_100g or grams - only the four macro
columns. Idempotent: an entry that already has non-null macros, or whose grams is
null (nothing to scale a per-100g value by), is left untouched, so this is safe to
interrupt and re-run. Cost scales with the number of distinct food descriptions
that need resolving, not the number of entries, since entries sharing a description
share one resolution.

Every food already logged before this change has a ResolutionCache row from before
the macro columns existed, and `resolve_food_energy`'s normal cache-hit path would
return that stale, macro-null entry forever without ever re-resolving it - so this
script calls `refresh_cached_macros` first, which patches just the macro columns
onto an existing cache row (kcal_per_100g/provenance untouched), and only falls
back to a full `resolve_food_energy` for a description with no cache entry at all.

Usage:
    uv run python scripts/backfill_macros.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.food.resolver import refresh_cached_macros, resolve_food_energy
from calobot.llm.gateway import LLMGateway
from calobot.persistence.engine import get_session_factory, init_engine
from calobot.persistence.models import FoodEntry
from calobot.settings import get_settings

logger = logging.getLogger(__name__)


def _scale(per_100g: float | None, grams: float | None) -> float | None:
    if per_100g is None or grams is None:
        return None
    return per_100g * grams / 100.0


async def backfill_macros(session: AsyncSession, gateway: LLMGateway) -> int:
    """Updates macro columns in place on `session` (caller commits/rolls back).
    Returns the number of entries updated."""
    result = await session.execute(
        select(FoodEntry).where(
            FoodEntry.deleted_at.is_(None),
            FoodEntry.grams.is_not(None),
            FoodEntry.protein_g.is_(None),
            FoodEntry.fat_g.is_(None),
            FoodEntry.carbs_g.is_(None),
            FoodEntry.fiber_g.is_(None),
        )
    )
    entries = list(result.scalars().all())
    if not entries:
        return 0

    by_description: dict[str, list[FoodEntry]] = {}
    for entry in entries:
        by_description.setdefault(entry.description, []).append(entry)

    logger.info(
        "%d entries across %d distinct descriptions need a macro resolution",
        len(entries),
        len(by_description),
    )

    updated = 0
    for description, group in by_description.items():
        energy = await refresh_cached_macros(session, gateway, description)
        if energy is None:
            energy = await resolve_food_energy(session, gateway, description)
        if all(
            v is None
            for v in (
                energy.protein_per_100g,
                energy.fat_per_100g,
                energy.carbs_per_100g,
                energy.fiber_per_100g,
            )
        ):
            logger.info("no macros resolvable for %r - leaving as null", description)
            continue

        for entry in group:
            entry.protein_g = _scale(energy.protein_per_100g, entry.grams)
            entry.fat_g = _scale(energy.fat_per_100g, entry.grams)
            entry.carbs_g = _scale(energy.carbs_per_100g, entry.grams)
            entry.fiber_g = _scale(energy.fiber_per_100g, entry.grams)
        updated += len(group)

    await session.flush()
    return updated


async def _run(dry_run: bool) -> None:
    settings = get_settings()
    init_engine(settings.database_url)
    gateway = LLMGateway(settings)
    session_factory = get_session_factory()

    async with session_factory() as session:
        updated = await backfill_macros(session, gateway)
        if dry_run:
            await session.rollback()
            print(f"Dry run: would update {updated} entries. No changes committed.")
        else:
            await session.commit()
            print(f"Updated {updated} entries.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Resolve macros but do not commit changes."
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run(args.dry_run))


if __name__ == "__main__":
    main()
