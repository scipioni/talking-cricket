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
