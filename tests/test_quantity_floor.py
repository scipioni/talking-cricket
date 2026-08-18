"""A quantity must be an amount, not merely a value that is present
(specs/message-ingestion - A stored entry carries a real quantity).

The defect these cover: `resolve_quantity` tested `is not None`, so a dictated zero
resolved cleanly and an entry of 0 g was stored. Weight had a plausibility band from
the start, which is why an absurd weight was always refused while an absurd portion
was not - the asymmetry was the defect, and these hold the two paths to the same rule.
"""

from __future__ import annotations

import pytest
from harness.state import create_onboarded_user, food_extraction
from sqlalchemy import select

from calobot.activity.planner import apply_answer as activity_apply_answer
from calobot.food.planner import apply_answer as food_apply_answer
from calobot.food.quantities import resolve_quantity
from calobot.ingestion.quantities import is_real_quantity
from calobot.ingestion.schemas import FoodItemExtraction
from calobot.persistence.models import ActivityEntry, FoodEntry
from calobot.persistence.seed import seed_all


def _item(**overrides) -> FoodItemExtraction:
    defaults = dict(
        description="cena",
        quantity_grams=None,
        quantity_count=None,
        count_unit_hint=None,
        household_measure=None,
        preparation=None,
        preparation_material_but_unstated=False,
    )
    return FoodItemExtraction(**{**defaults, **overrides})


# -- the rule itself ------------------------------------------------------


@pytest.mark.parametrize("value", [None, 0, 0.0, -1, -250.5])
def test_an_unreal_amount_is_not_a_quantity(value):
    assert not is_real_quantity(value)


@pytest.mark.parametrize("value", [0.5, 1, 10, 5000])
def test_a_real_amount_is_a_quantity(value):
    assert is_real_quantity(value)


# -- resolution -----------------------------------------------------------


def test_zero_grams_does_not_resolve():
    assert resolve_quantity(_item(quantity_grams=0)) is None


def test_negatives_cannot_even_reach_resolution():
    """Defence in depth already present: the extraction schema constrains grams to
    `ge=0`, so a negative fails validation and is retried before resolution sees it.
    Zero is the case that gets through, which is why the floor lives here as well.
    The schema deliberately still admits zero: rejecting it there would exhaust the
    retry budget and end in "rephrase your message", where the right answer is to ask
    for the portion."""
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        _item(quantity_grams=-100)


def test_zero_count_does_not_resolve():
    assert resolve_quantity(_item(quantity_count=0, count_unit_hint="mela")) is None


def test_a_real_quantity_still_resolves():
    resolved = resolve_quantity(_item(quantity_grams=120))
    assert resolved is not None and resolved.grams == 120


def test_a_real_count_still_resolves():
    resolved = resolve_quantity(_item(quantity_count=2, count_unit_hint="mela"))
    assert resolved is not None and resolved.grams == 360


def test_a_count_of_small_countable_items_still_resolves():
    """Regression test: "2 noci" (2 walnuts) used to fall through to the generic
    80/120/180g portion-size clarification - sizes tuned for a whole fruit, not a
    couple of walnuts - because "noce" was missing from TYPICAL_UNIT_WEIGHTS_G, even
    though a real count was already given."""
    resolved = resolve_quantity(_item(quantity_count=2, count_unit_hint="noce"))
    assert resolved is not None and resolved.grams == 10


def test_the_plural_form_of_a_countable_item_still_resolves():
    """Regression test: the extraction prompt asks the model for the singular hint,
    but it does not reliably comply - "2 noci" as spoken by the user reaches here
    with count_unit_hint="noci" just as often as the singular "noce", and only the
    singular used to be in TYPICAL_UNIT_WEIGHTS_G."""
    resolved = resolve_quantity(_item(quantity_count=2, count_unit_hint="noci"))
    assert resolved is not None and resolved.grams == 10


@pytest.mark.parametrize("hint", ["mandorla", "mandorle"])
def test_almonds_resolve_in_either_grammatical_number(hint):
    """Regression test: "3 mandorle" surfaced the generic 80/120/180g portion
    clarification - sizes meant for a whole fruit, nonsensical for a handful of
    almonds - because "mandorla" was entirely absent from TYPICAL_UNIT_WEIGHTS_G."""
    resolved = resolve_quantity(_item(quantity_count=3, count_unit_hint=hint))
    assert resolved is not None and resolved.grams == pytest.approx(3.6)


# -- the clarification answer path ----------------------------------------


def test_zero_typed_as_a_portion_answer_leaves_the_field_unresolved():
    """Unresolved rather than rejected: check_item then asks again, instead of the
    draft becoming complete with a meaningless number."""
    item = {"description": "riso", "resolved": {}}

    updated = food_apply_answer(item, "portion_grams", "0 grammi")

    assert "portion_grams" not in updated["resolved"]


def test_a_real_portion_answer_is_still_accepted():
    item = {"description": "riso", "resolved": {}}

    updated = food_apply_answer(item, "portion_grams", "150 grammi")

    assert updated["resolved"]["portion_grams"] == 150


def test_zero_typed_as_a_duration_answer_leaves_the_field_unresolved():
    item = {"activity_description": "corsa", "resolved": {}}

    updated = activity_apply_answer(item, "duration_minutes", "0 minuti")

    assert "duration_minutes" not in updated["resolved"]


# -- end to end -----------------------------------------------------------


async def test_a_dictated_zero_asks_instead_of_storing(db_session, client, llm):
    """Task 1.4: the rejected value enters the clarification loop rather than
    producing an error with nowhere to go."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="cena", quantity_grams=0),
    )

    sent = await client.say("registra 0 calorie per la cena")

    db_session.expire_all()
    entries = list((await db_session.execute(select(FoodEntry))).scalars())
    assert entries == []
    assert sent[-1].options, "the bot should be asking for the portion"
    assert "cena" in sent[-1].text.lower()


async def test_a_dictated_zero_duration_asks_instead_of_storing(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "activity", "ignored_text": None},
        {"activity_description": "corsa", "duration_minutes": 0, "intensity_text": None, "when_text": None},
    )

    sent = await client.say("registra 0 minuti di corsa")

    db_session.expire_all()
    assert list((await db_session.execute(select(ActivityEntry))).scalars()) == []
    assert sent[-1].options


async def test_answering_the_portion_question_after_a_zero_still_stores(db_session, client, llm):
    """The loop is not a dead end: a real answer after a rejected one completes the
    draft normally."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="riso", quantity_grams=0),
    )
    asked = await client.say("registra 0 grammi di riso")
    assert asked[-1].options

    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 130, "display_name_it": "riso"},
    )
    stored = await client.tap(asked[-1].labels[1])

    db_session.expire_all()
    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert entry.grams > 0
    assert "🗑 elimina" in stored[-1].options
