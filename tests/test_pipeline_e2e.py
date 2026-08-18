"""End-to-end tests with a scripted language model (no live endpoint is needed to
run the suite). Exercises the real classify -> extract -> draft -> resolve -> store
path, driven through the transport double so that what a test does is what a user
could do: buttons are tapped, not typed.

Before the double existed, a button answer was fed back as free text - which happens
to work only because the clarification loop also accepts free text, and left the
answer-callback handler untested for food and activity.
"""

from __future__ import annotations

from harness.state import create_onboarded_user, food_extraction

from calobot.persistence.seed import seed_all


async def test_food_with_explicit_grams_resolves_from_table(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="noci", quantity_grams=10),
        {"selected_candidate_id": 1},  # matches the seeded Walnuts row
    )

    sent = await client.say("ho mangiato 10g di noci")

    assert len(sent) == 1
    assert "noci" in sent[0].text
    assert "🗑 elimina" in sent[0].options  # entry controls attached, so it was stored


async def test_food_with_vague_portion_asks_then_stores(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="pasta al pesto", quantity_grams=None, household_measure="un piatto"
        ),
    )

    sent = await client.say("un piatto di pasta al pesto")

    assert len(sent) == 1
    assert sent[0].options  # asked for a portion with tappable options
    offered = sent[0].labels

    # The user taps the middle option, as a real client would.
    llm.push(
        {"selected_candidate_id": None},  # no table match -> estimate
        {"kcal_per_100g": 200, "display_name_it": "pasta al pesto"},
    )
    follow_up = await client.tap(offered[1])

    assert len(follow_up) == 1
    assert "stima" in follow_up[0].text
    assert "🗑 elimina" in follow_up[0].options


async def test_vague_portion_options_are_scaled_to_the_food(db_session, client, llm):
    """A condiment and a plate of pasta don't share a portion scale: when extraction
    supplies food-specific estimates alongside the household measure, those - not the
    generic 80/120/180g buttons - are what gets offered and stored."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="maionese",
            quantity_grams=None,
            household_measure="un cucchiaio",
            portion_small_g=10,
            portion_medium_g=20,
            portion_generous_g=40,
        ),
    )

    sent = await client.say("un cucchiaio di maionese")

    assert sent[0].labels[:3] == ["piccolo (~10g)", "medio (~20g)", "abbondante (~40g)"]

    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 680, "display_name_it": "maionese"},
    )
    follow_up = await client.tap(sent[0].labels[1])

    assert "20g" in follow_up[0].text


async def test_preparation_options_are_scaled_to_the_food(db_session, client, llm):
    """Deciding that preparation matters for this food already means knowing which
    preparations - so an egg is asked about as an egg, not offered the generic
    fry/boil/bake/grill list that describes none of the ways one is actually cooked."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="uovo",
            quantity_grams=55,
            preparation_material_but_unstated=True,
            preparation_options=["sodo", "strapazzato", "in camicia", "fritto"],
        ),
    )

    sent = await client.say("ho mangiato un uovo")

    assert sent[0].labels[:4] == ["sodo", "strapazzato", "in camicia", "fritto"]

    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 155, "display_name_it": "uovo sodo"},
    )
    follow_up = await client.tap("sodo")

    assert "🗑 elimina" in follow_up[0].options


async def test_a_single_countable_food_is_stored_without_asking(db_session, client, llm):
    """Reported from a live chat: "mangio una pesca" was met with the generic
    80/120/180g portion question, because the model names the food in description and
    leaves count_unit_hint null - which the resolver required."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="pesca",
            quantity_grams=None,
            quantity_count=1,
            count_unit_hint=None,
        ),
        {"selected_candidate_id": None},
        {"kcal_per_100g": 39, "display_name_it": "pesca"},
    )

    sent = await client.say("mangio una pesca")

    assert "150g" in sent[0].text
    assert "🗑 elimina" in sent[0].options  # stored outright, no question asked


async def test_a_count_of_an_unlisted_item_resolves_without_asking(db_session, client, llm):
    """The unit-weight table can't list every countable food; before the model's
    estimate backed it up, "3 datteri" fell through to the vague-portion question
    despite carrying a perfectly precise count."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="datteri",
            quantity_grams=None,
            quantity_count=3,
            count_unit_hint="dattero",
            typical_unit_weight_g=8,
        ),
        {"selected_candidate_id": None},
        {"kcal_per_100g": 282, "display_name_it": "datteri"},
    )

    sent = await client.say("ho mangiato 3 datteri")

    assert "24g" in sent[0].text
    assert "porzione stimata" in sent[0].text  # the assumption is stated back
    assert "🗑 elimina" in sent[0].options


async def test_weight_message_end_to_end(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42, weight_kg=90.0)

    llm.push(
        {"intent": "weight", "ignored_text": None},
        {"value_text": "89.5", "when_text": None},
        {"kg_absolute": 89.5, "delta_kg": None, "direction": None},
    )

    # A small, plausible change from the 90 kg logged at onboarding is stored directly.
    sent = await client.say("oggi peso 89,5")

    assert len(sent) == 1
    assert "89.5" in sent[0].text
    assert "🗑 elimina" in sent[0].options


async def test_report_message_end_to_end(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "food"},
    )

    sent = await client.say("report di oggi")

    assert len(sent) == 1
    assert "dati" in sent[0].text.lower()  # nothing logged -> "non ci sono dati"
