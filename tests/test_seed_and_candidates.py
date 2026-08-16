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


async def test_retrieve_met_candidates_finds_camminata(db_session):
    await seed_all(db_session)
    candidates = await retrieve_met_candidates(db_session, "camminata veloce")
    assert any(c.name_it == "camminata" for c in candidates)
