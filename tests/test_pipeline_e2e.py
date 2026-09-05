"""End-to-end tests with a scripted language model (no live endpoint is needed to
run the suite). Exercises the real classify -> extract -> draft -> resolve -> store
path, driven through the transport double so that what a test does is what a user
could do: buttons are tapped, not typed.

Before the double existed, a button answer was fed back as free text - which happens
to work only because the clarification loop also accepts free text, and left the
answer-callback handler untested for food and activity.
"""

from __future__ import annotations

from sqlalchemy import select

from harness.state import create_onboarded_user, food_extraction

from calobot.persistence.models import FoodEntry, User
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


async def test_food_with_explicit_grams_stores_macros_scaled_to_portion(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="noci", quantity_grams=10),
        {"selected_candidate_id": 1},  # matches the seeded Walnuts row
    )

    await client.say("ho mangiato 10g di noci")

    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert entry.protein_g == 1.52
    assert entry.fat_g == 6.52
    assert entry.carbs_g == 1.37
    assert entry.fiber_g == 0.67


async def test_food_with_vague_portion_asks_then_stores(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="pasta al pesto", quantity_grams=None, household_measure="un piatto"),
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


async def test_macro_report_with_no_data(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "macros"},
    )

    sent = await client.say("distribuzione di proteine, grassi, carboidrati e fibre di oggi")

    assert len(sent) == 1
    assert "macronutrienti" in sent[0].text.lower()
    assert "non ci sono dati" in sent[0].text.lower()


async def test_macro_report_over_a_week_sends_a_chart(db_session, client, llm):
    from calobot.persistence.models import FoodEntry, Provenance
    from calobot.persistence.repository import get_user_by_telegram_id
    from calobot.persistence.timeutil import utcnow

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    user = await get_user_by_telegram_id(db_session, 42)

    db_session.add(
        FoodEntry(
            user_id=user.id,
            description="noci",
            grams=10,
            kcal_per_100g=654,
            kcal=65.4,
            protein_g=1.52,
            fat_g=6.52,
            carbs_g=1.37,
            fiber_g=0.67,
            provenance=Provenance.tabella,
            consumed_at=utcnow(),
        )
    )
    await db_session.flush()

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": "questa settimana", "topic": "macros"},
    )

    sent = await client.say("il grafico della distribuzione di proteine, grassi, carboidrati e fibre di questa settimana")

    assert len(sent) == 1
    assert "macronutrienti" in sent[0].text.lower()
    assert "proteine 2g" in sent[0].text.lower()
    assert sent[0].has_image


async def test_report_daily_rolling_average_and_weight_formatting(db_session, client, llm):
    import datetime as dt
    from zoneinfo import ZoneInfo

    from calobot.persistence.models import FoodEntry, Provenance
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
        {"advice": "Prova a includere una fonte proteica per il resto della giornata."},
    )

    sent = await client.say("report di oggi")

    # Calories and weight only: no activity was logged, and an unscoped report does not
    # announce the absence (specs/reporting - An unscoped report reports only the topics
    # that have data).
    assert len(sent) == 2

    # Food report assertions
    food_msg = next(msg for msg in sent if "Calorie" in msg.text)
    assert "totale 467 kcal" in food_msg.text
    assert "media giornaliera 500 kcal" in food_msg.text
    assert "Prova a includere una fonte proteica" in food_msg.text

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


async def test_daily_report_shows_activity_credit_when_activity_logged(db_session, client, llm):
    import datetime as dt
    from zoneinfo import ZoneInfo

    from calobot.persistence.models import ActivityEntry, FoodEntry, Provenance
    from calobot.profile.service import current_budget

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tz = ZoneInfo("Europe/Rome")
    today = dt.datetime.now(tz)

    db_session.add(
        FoodEntry(
            user_id=user.id,
            description="mela",
            grams=150,
            kcal_per_100g=52,
            kcal=78.0,
            provenance=Provenance.tabella,
            consumed_at=today,
        )
    )
    db_session.add(
        ActivityEntry(
            user_id=user.id,
            activity="camminata",
            duration_minutes=120,
            met=4.0,
            kcal=800.0,
            provenance=Provenance.tabella,
            performed_at=today,
        )
    )
    await db_session.flush()

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "food"},
        {"advice": "Prova ad aggiungere una fonte proteica stasera."},
    )

    sent = await client.say("report di oggi")

    assert len(sent) == 1
    text = sent[0].text

    budget = await current_budget(db_session, user)
    expected_credit = min(0.5 * 800.0, 600.0)
    expected_diff = 78.0 - (budget.target_kcal + expected_credit)

    assert f"{expected_credit:.0f} credito attività" in text
    assert f"differenza {expected_diff:+.0f}" in text
    assert "Prova ad aggiungere una fonte proteica stasera." in text


async def test_daily_report_text_unchanged_with_no_activity_logged(db_session, client, llm):
    import datetime as dt
    from zoneinfo import ZoneInfo

    from calobot.persistence.models import FoodEntry, Provenance
    from calobot.profile.service import current_budget

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tz = ZoneInfo("Europe/Rome")
    today = dt.datetime.now(tz)

    db_session.add(
        FoodEntry(
            user_id=user.id,
            description="mela",
            grams=150,
            kcal_per_100g=52,
            kcal=78.0,
            provenance=Provenance.tabella,
            consumed_at=today,
        )
    )
    await db_session.flush()

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "food"},
        {"advice": "Continua così."},
    )

    sent = await client.say("report di oggi")

    assert len(sent) == 1
    text = sent[0].text

    budget = await current_budget(db_session, user)
    expected_diff = 78.0 - budget.target_kcal

    assert "credito attività" not in text
    assert f"differenza {expected_diff:+.0f})" in text


async def test_daily_report_omits_advice_line_when_advice_call_fails(db_session, client, llm):
    import datetime as dt
    from zoneinfo import ZoneInfo

    from calobot.persistence.models import FoodEntry, Provenance
    from calobot.profile.service import current_budget

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tz = ZoneInfo("Europe/Rome")
    today = dt.datetime.now(tz)

    db_session.add(
        FoodEntry(
            user_id=user.id,
            description="mela",
            grams=150,
            kcal_per_100g=52,
            kcal=78.0,
            provenance=Provenance.tabella,
            consumed_at=today,
        )
    )
    await db_session.flush()

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "food"},
        RuntimeError("boom"),
    )

    sent = await client.say("report di oggi")

    assert len(sent) == 1
    text = sent[0].text

    budget = await current_budget(db_session, user)
    expected_diff = 78.0 - budget.target_kcal

    assert f"differenza {expected_diff:+.0f})" in text
    assert "💡" not in text


async def test_new_food_cancels_existing_draft_even_if_it_has_a_number(db_session, client, llm):
    from sqlalchemy import select

    from calobot.persistence.models import FoodEntry

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    # 1. User says "ho mangiato un avocado" (which lacks a portion weight)
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="avocado", quantity_grams=None, household_measure="un frutto"),
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


async def test_cooked_pasta_preparation_preserved_and_resolved(db_session, client, llm):
    from sqlalchemy import select

    from calobot.persistence.models import FoodEntry

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    # User logs 180g of cooked pasta.
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="pasta",
            quantity_grams=180,
            preparation="cotta",
        ),
        # Since the preparation is already "cotta", it is appended to form "pasta cotta"
        # and used to match candidates. "Pasta cooked" (id=60) matches perfectly.
        {"selected_candidate_id": 60},
    )

    sent = await client.say("180g di pasta pesata cotta")

    assert len(sent) == 1
    # Check that "pasta cotta" and correct calories (180 * 1.58 = 284.4 -> ~284 kcal) are registered
    assert "pasta cotta" in sent[0].text.lower()
    assert "284 kcal" in sent[0].text

    # Verify what was stored in the database
    db_session.expire_all()
    entries = list((await db_session.execute(select(FoodEntry))).scalars())
    assert len(entries) == 1
    assert entries[0].description == "pasta cotta"
    assert entries[0].kcal_per_100g == 158.0
    assert entries[0].kcal == 284.4


async def test_conversational_nudge_enable_end_to_end(db_session, client, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    assert user.nudges_enabled is False

    llm.push(
        {"intent": "nudges", "ignored_text": None},
        {"action": "enable"},
    )

    sent = await client.say("voglio ricevere le notifiche")

    assert len(sent) == 1
    assert "attivate" in sent[0].text
    user_id = user.id
    db_session.expire_all()
    refreshed = await db_session.get(User, user_id)
    assert refreshed.nudges_enabled is True


async def test_conversational_nudge_disable_end_to_end(db_session, client, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user.nudges_enabled = True
    await db_session.commit()

    llm.push(
        {"intent": "nudges", "ignored_text": None},
        {"action": "disable"},
    )

    sent = await client.say("basta notifiche")

    assert len(sent) == 1
    assert "disattivate" in sent[0].text
    user_id = user.id
    db_session.expire_all()
    refreshed = await db_session.get(User, user_id)
    assert refreshed.nudges_enabled is False


async def test_conversational_nudge_toggle_is_idempotent_in_its_reply(db_session, client, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user.nudges_enabled = True
    await db_session.commit()

    llm.push(
        {"intent": "nudges", "ignored_text": None},
        {"action": "enable"},
    )

    sent = await client.say("voglio ricevere le notifiche")

    assert "già attivate" in sent[0].text  # the truth: nothing changed
