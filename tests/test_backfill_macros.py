"""scripts/backfill_macros.py: resolves macros for pre-existing FoodEntry rows
without touching kcal/kcal_per_100g/grams, and is idempotent. See
openspec/changes/add-macro-nutrient-tracking/tasks.md 6.1-6.2."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from backfill_macros import backfill_macros  # noqa: E402

from calobot.food.resolver import normalize_description
from calobot.persistence.models import FoodEntry, Provenance, ResolutionCache
from calobot.persistence.repository import create_user
from calobot.persistence.seed import seed_all
from calobot.persistence.timeutil import utcnow


async def _make_entry(session, user_id, **overrides) -> FoodEntry:
    defaults = dict(
        user_id=user_id,
        description="noci",
        grams=10.0,
        kcal_per_100g=654.0,
        kcal=65.4,
        provenance=Provenance.tabella,
        consumed_at=utcnow(),
    )
    defaults.update(overrides)
    entry = FoodEntry(**defaults)
    session.add(entry)
    await session.flush()
    return entry


async def test_backfill_resolves_macros_and_leaves_kcal_and_grams_unchanged(db_session, llm):
    await seed_all(db_session)
    user = await create_user(db_session, telegram_user_id=1)
    entry = await _make_entry(db_session, user.id)

    llm.push({"selected_candidate_id": 1})  # matches the seeded Walnuts row

    updated = await backfill_macros(db_session, llm.gateway)
    await db_session.commit()

    assert updated == 1
    refreshed = (await db_session.execute(select(FoodEntry).where(FoodEntry.id == entry.id))).scalar_one()
    assert refreshed.kcal == 65.4
    assert refreshed.kcal_per_100g == 654.0
    assert refreshed.grams == 10.0
    assert refreshed.protein_g == 1.52
    assert refreshed.fat_g == 6.52
    assert refreshed.carbs_g == 1.37
    assert refreshed.fiber_g == 0.67


async def test_backfill_is_idempotent(db_session, llm):
    await seed_all(db_session)
    user = await create_user(db_session, telegram_user_id=2)
    await _make_entry(db_session, user.id)

    llm.push({"selected_candidate_id": 1})

    first_run = await backfill_macros(db_session, llm.gateway)
    await db_session.commit()
    assert first_run == 1

    # No response staged for a second run: if it made another LLM/candidate call,
    # the scripted gateway would raise NoScriptedResponse.
    second_run = await backfill_macros(db_session, llm.gateway)
    await db_session.commit()
    assert second_run == 0


async def test_backfill_refreshes_a_pre_existing_cache_entry_with_null_macros(db_session, llm):
    """The real bug this guards against: a food logged before add-macro-nutrient-
    tracking already has a ResolutionCache row with null macros. resolve_food_energy's
    cache-hit path would return that stale entry forever - backfill must patch the
    cache's macro columns instead of trusting the cache hit as-is."""
    await seed_all(db_session)
    user = await create_user(db_session, telegram_user_id=4)
    entry = await _make_entry(db_session, user.id)

    db_session.add(
        ResolutionCache(
            normalized_key=normalize_description("noci"),
            kcal_per_100g=654.0,
            provenance=Provenance.tabella,
            display_name_it="noci",
        )
    )
    await db_session.flush()

    llm.push({"selected_candidate_id": 1})  # matches the seeded Walnuts row

    updated = await backfill_macros(db_session, llm.gateway)
    await db_session.commit()

    assert updated == 1
    refreshed = (await db_session.execute(select(FoodEntry).where(FoodEntry.id == entry.id))).scalar_one()
    assert refreshed.kcal == 65.4  # untouched
    assert refreshed.protein_g == 1.52
    assert refreshed.fat_g == 6.52

    cache_row = await db_session.get(ResolutionCache, normalize_description("noci"))
    assert cache_row.kcal_per_100g == 654.0  # untouched
    assert cache_row.provenance == Provenance.tabella  # untouched
    assert cache_row.protein_per_100g == 15.2


async def test_backfill_skips_entries_with_unresolved_grams(db_session, llm):
    await seed_all(db_session)
    user = await create_user(db_session, telegram_user_id=3)
    entry = await _make_entry(db_session, user.id, grams=None, kcal=65.4)

    updated = await backfill_macros(db_session, llm.gateway)
    await db_session.commit()

    assert updated == 0
    refreshed = (await db_session.execute(select(FoodEntry).where(FoodEntry.id == entry.id))).scalar_one()
    assert refreshed.protein_g is None
    assert refreshed.kcal == 65.4
