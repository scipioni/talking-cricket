"""A calorie value the user states directly must be stored as-is, not silently
discarded in favour of a value computed forward from an assumed gram quantity
(specs/food-logging - Calorie value stated directly). The defect this covers: "100kcal
di melanzane sott'olio" used to be extracted as quantity_grams=100 and confirmed back
as "100g - 25 kcal", because the extraction schema had no slot for a stated calorie
value at all.
"""

from __future__ import annotations

import pytest
from harness.state import create_onboarded_user, food_extraction
from sqlalchemy import select

from calobot.food.planner import finalize_item
from calobot.persistence.models import FoodEntry
from calobot.persistence.seed import seed_all


async def test_stated_kcal_wins_over_a_recomputed_value(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="melanzane sott'olio",
            stated_kcal=100,
            quantity_grams=None,
        ),
    )
    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 25, "display_name_it": "melanzane sott'olio"},
    )

    sent = await client.say("100kcal di melanzane sott'olio")

    db_session.expire_all()
    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert entry.kcal == 100
    assert entry.grams == pytest.approx(400.0)  # 100 kcal / 25 kcal-per-100g * 100

    text = sent[-1].text
    assert "100 kcal" in text
    assert "25 kcal" not in text


async def test_stated_kcal_with_unresolvable_density_leaves_grams_unknown(
    db_session, client, llm
):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="misteriosa sostanza",
            stated_kcal=50,
            quantity_grams=None,
        ),
    )
    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 0, "display_name_it": "misteriosa sostanza"},
    )

    sent = await client.say("50kcal di misteriosa sostanza")

    db_session.expire_all()
    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert entry.kcal == 50
    assert entry.grams is None

    text = sent[-1].text
    assert "50 kcal" in text
    assert "non stimabili" in text


async def test_the_grams_first_path_is_unaffected(db_session, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 654, "display_name_it": "noci"},
    )

    item = {
        "description": "noci",
        "stated_kcal": None,
        "when_text": None,
        "resolved": {"portion_grams": 10.0},
    }

    finalized = await finalize_item(
        db_session, llm.gateway, user_id=user.id, item=item, tz="Europe/Rome"
    )

    assert finalized.kcal_is_stated is False
    assert finalized.entry.grams == 10.0
    assert finalized.entry.kcal == pytest.approx(65.4)
