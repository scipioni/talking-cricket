from __future__ import annotations

from calobot.persistence.candidates import retrieve_food_candidates, retrieve_met_candidates
from calobot.persistence.seed import seed_all


async def test_seed_is_idempotent(db_session):
    await seed_all(db_session)
    from calobot.persistence.models import FoodDataRow

    count_after_first = len((await db_session.execute(FoodDataRow.__table__.select())).all())

    await seed_all(db_session)
    count_after_second = len((await db_session.execute(FoodDataRow.__table__.select())).all())

    assert count_after_first == count_after_second
    assert count_after_first > 100


async def test_retrieve_food_candidates_finds_noci(db_session):
    await seed_all(db_session)
    candidates = await retrieve_food_candidates(db_session, "noci")
    names = [c.source_name_en for c in candidates]
    assert any("walnuts" in name.lower() for name in names)


async def test_seed_backfills_macros_onto_a_row_seeded_before_macros_existed(db_session):
    from calobot.persistence.models import FoodDataRow

    # Simulates a row seeded before add-macro-nutrient-tracking: present by name,
    # macro columns still null, as seed_food_data used to leave it forever since it
    # only inserted missing rows.
    db_session.add(
        FoodDataRow(
            source_name_en="Nuts, walnuts, english",
            kcal_per_100g=654.0,
            aliases_it="noci;noce;gherigli di noce",
        )
    )
    await db_session.flush()

    await seed_all(db_session)

    result = await db_session.execute(
        FoodDataRow.__table__.select().where(FoodDataRow.source_name_en == "Nuts, walnuts, english")
    )
    row = result.one()
    assert row.protein_per_100g is not None
    assert row.fat_per_100g is not None


async def test_retrieve_food_candidates_carries_macros(db_session):
    await seed_all(db_session)
    candidates = await retrieve_food_candidates(db_session, "noci")
    walnuts = next(c for c in candidates if "walnuts" in c.source_name_en.lower())
    assert walnuts.protein_per_100g is not None
    assert walnuts.fat_per_100g is not None
    assert walnuts.carbs_per_100g is not None
    assert walnuts.fiber_per_100g is not None


async def test_retrieve_met_candidates_finds_camminata(db_session):
    await seed_all(db_session)
    candidates = await retrieve_met_candidates(db_session, "camminata veloce")
    assert any(c.name_it == "camminata" for c in candidates)


async def test_retrieve_met_candidates_finds_bicicletta_elettrica(db_session):
    await seed_all(db_session)
    candidates = await retrieve_met_candidates(db_session, "bicicletta elettrica")
    assert any(c.name_it == "bicicletta elettrica" for c in candidates)
