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


async def test_report_daily_rolling_average_and_weight_formatting(db_session, client, llm):
    import datetime as dt
    from zoneinfo import ZoneInfo
    from calobot.persistence.models import FoodEntry, WeightEntry, Provenance
    from calobot.profile.service import current_budget

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42, weight_kg=76.0)
    user.peso_obiettivo_kg = 75.0

    tz = ZoneInfo("Europe/Rome")
    today = dt.datetime.now(tz)
    yesterday = today - dt.timedelta(days=1)

    db_session.add(
        FoodEntry(
            user_id=user.id,
            description="mela",
            grams=100,
            kcal_per_100g=52,
            kcal=467.0,
            provenance=Provenance.tabella,
            consumed_at=today,
        )
    )
    db_session.add(
        FoodEntry(
            user_id=user.id,
            description="banana",
            grams=100,
            kcal_per_100g=89,
            kcal=533.0,
            provenance=Provenance.tabella,
            consumed_at=yesterday,
        )
    )
    await db_session.flush()

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "all"},
    )

    sent = await client.say("report di oggi")

    assert len(sent) == 3

    # Food report assertions
    food_msg = next(msg for msg in sent if "Calorie" in msg.text)
    assert "totale 467 kcal" in food_msg.text
    assert "media giornaliera 500 kcal" in food_msg.text

    budget = await current_budget(db_session, user)
    budget_kcal = budget.target_kcal if budget else None
    if budget_kcal is not None:
        expected_diff = 467.0 - budget_kcal
        assert f"differenza {expected_diff:+.0f}" in food_msg.text

    # Weight report assertions
    weight_msg = next(msg for msg in sent if "Peso" in msg.text)
    assert "Peso (day): 76.0 kg" in weight_msg.text
    assert "da 76.0 a 76.0 kg" not in weight_msg.text
    assert "mancano -1.0 kg" in weight_msg.text or "mancano 1.0 kg" in weight_msg.text


async def test_new_food_cancels_existing_draft_even_if_it_has_a_number(db_session, client, llm):
    from sqlalchemy import select
    from calobot.persistence.models import FoodEntry

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    # 1. User says "ho mangiato un avocado" (which lacks a portion weight)
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="avocado", quantity_grams=None, household_measure="un frutto"
        ),
    )
    first_reply = await client.say("ho mangiato un avocado")
    assert "avocado" in first_reply[0].text
    assert first_reply[0].options  # Clarification prompt with buttons is shown

    # 2. User replies with a COMPLETELY new food logging containing a number: "Cetriolo 10g"
    # This should:
    # - classify the new text (not simple portion text -> classif. is "food")
    # - extract the food (it finds "cetriolo", which doesn't match draft's "avocado")
    # - discard the avocado draft and output cancellation notice
    # - process "Cetriolo 10g" freshly: classify -> extract -> resolve candidates -> resolve energy
    cetriolo_ext = food_extraction(description="cetriolo", quantity_grams=10)
    
    llm.push(
        # Under open draft: classify the input "Cetriolo 10g"
        {"intent": "food", "ignored_text": None},
        # Under open draft: extract the food from "Cetriolo 10g" to check if different
        cetriolo_ext,
        # Under fresh handling: classify "Cetriolo 10g"
        {"intent": "food", "ignored_text": None},
        # Under fresh handling: extract food
        cetriolo_ext,
        # Resolve candidates
        {"selected_candidate_id": None},
        # Resolve energy
        {"kcal_per_100g": 16, "display_name_it": "cetriolo"},
    )

    follow_up = await client.say("Cetriolo 10g")

    # Should have 2 replies:
    # 1. Notice of cancellation
    # 2. Cetriolo registration confirmation
    assert len(follow_up) == 2
    assert "annullato la richiesta precedente" in follow_up[0].text
    assert "cetriolo" in follow_up[1].text.lower()
    assert "10g" in follow_up[1].text
    assert "2 kcal" in follow_up[1].text

    # Let's verify that ONLY Cetriolo was stored, and Avocado was NOT stored!
    db_session.expire_all()
    entries = list((await db_session.execute(select(FoodEntry))).scalars())
    assert len(entries) == 1
    assert entries[0].description == "cetriolo"
    assert entries[0].grams == 10

