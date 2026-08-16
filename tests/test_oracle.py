"""Tests for the oracle itself (task 6.6).

The oracle decides whether a run passed. If it is wrong, every simulation result is
wrong in the same direction and nobody notices, so it is tested both ways round: a
step that should pass and a step that should fail, for each expectation type.
"""

from __future__ import annotations

import datetime as dt

import pytest
from harness.oracle import score, snapshot
from harness.scenario import (
    AskedAgain,
    DeclinedAndRedirected,
    NothingStored,
    Step,
    StoredFood,
    StoredWeight,
)
from harness.state import create_onboarded_user, food_extraction
from harness.transport import SentMessage

from calobot.persistence.seed import seed_all


def _reply(text: str, options: dict[str, str] | None = None) -> SentMessage:
    return SentMessage(message_id=1, chat_id=42, text=text, options=options or {})


async def _score(db_session, user_id, settings, step, before, after, replies):
    return await score(
        db_session,
        user_id,
        settings.timezone,
        step_index=1,
        step=step,
        said="qualcosa",
        replies=replies,
        before=before,
        after=after,
    )


async def _log_food(client, llm, description: str, grams: int):
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description=description, quantity_grams=grams),
        {"selected_candidate_id": None},
        {"kcal_per_100g": 100, "display_name_it": description},
    )
    return await client.say(f"{grams}g di {description}")


# -- stored food ----------------------------------------------------------


async def test_a_matching_stored_entry_passes(db_session, client, llm, settings):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id

    before = await snapshot(db_session, user_id)
    replies = await _log_food(client, llm, "riso", 100)
    after = await snapshot(db_session, user_id)

    step = Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))
    verdict = await _score(db_session, user_id, settings, step, before, after, replies)

    assert verdict.passed, verdict.detail


async def test_the_wrong_quantity_fails(db_session, client, llm, settings):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id

    before = await snapshot(db_session, user_id)
    replies = await _log_food(client, llm, "riso", 10)  # the bot stored a tenth
    after = await snapshot(db_session, user_id)

    step = Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))
    verdict = await _score(db_session, user_id, settings, step, before, after, replies)

    assert not verdict.passed
    assert "10 g" in verdict.detail


async def test_the_wrong_food_fails(db_session, client, llm, settings):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id

    before = await snapshot(db_session, user_id)
    replies = await _log_food(client, llm, "pollo", 100)
    after = await snapshot(db_session, user_id)

    step = Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))
    verdict = await _score(db_session, user_id, settings, step, before, after, replies)

    assert not verdict.passed
    assert "pollo" in verdict.detail


async def test_a_small_difference_is_tolerated(db_session, client, llm, settings):
    """Coarse by design: holding the bot to an exact figure would fail every
    reasonable resolution of a household portion."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id

    before = await snapshot(db_session, user_id)
    replies = await _log_food(client, llm, "riso", 110)
    after = await snapshot(db_session, user_id)

    step = Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))
    verdict = await _score(db_session, user_id, settings, step, before, after, replies)

    assert verdict.passed


async def test_the_wrong_local_day_fails(db_session, client, llm, settings, clock):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id
    clock.set_local(dt.datetime(2026, 3, 2, 13, 0), settings.timezone)

    before = await snapshot(db_session, user_id)
    replies = await _log_food(client, llm, "riso", 100)
    after = await snapshot(db_session, user_id)

    step = Step(
        intent="log rice yesterday",
        expect=StoredFood("riso", 100, on_local_day=dt.date(2026, 3, 1)),
    )
    verdict = await _score(db_session, user_id, settings, step, before, after, replies)

    assert not verdict.passed
    assert "2026-03-02" in verdict.detail


# -- nothing stored -------------------------------------------------------


async def test_nothing_stored_passes_when_nothing_was_stored(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id
    before = after = await snapshot(db_session, user_id)

    step = Step(intent="claim an absurd weight", expect=NothingStored())
    verdict = await _score(
        db_session, user_id, settings, step, before, after, [_reply("non è plausibile")]
    )

    assert verdict.passed


async def test_nothing_stored_fails_when_something_was_stored(
    db_session, client, llm, settings
):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id

    before = await snapshot(db_session, user_id)
    replies = await _log_food(client, llm, "riso", 100)
    after = await snapshot(db_session, user_id)

    step = Step(intent="say something unloggable", expect=NothingStored())
    verdict = await _score(db_session, user_id, settings, step, before, after, replies)

    assert not verdict.passed


# -- asked again ----------------------------------------------------------


async def test_asked_again_passes_on_a_question_with_options(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id
    before = after = await snapshot(db_session, user_id)

    step = Step(intent="shrug at the portion question", expect=AskedAgain())
    verdict = await _score(
        db_session,
        user_id,
        settings,
        step,
        before,
        after,
        [_reply("Quanto era la porzione?", {"piccolo": "ans:piccolo"})],
    )

    assert verdict.passed


async def test_asked_again_fails_when_the_bot_invents_a_value(
    db_session, client, llm, settings
):
    """The dangerous failure: a confident, plausible, wrong number where a question
    should have been."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id

    before = await snapshot(db_session, user_id)
    replies = await _log_food(client, llm, "pasta", 120)
    after = await snapshot(db_session, user_id)

    step = Step(intent="shrug at the portion question", expect=AskedAgain())
    verdict = await _score(db_session, user_id, settings, step, before, after, replies)

    assert not verdict.passed
    assert "instead of a question" in verdict.detail


async def test_asked_again_fails_on_a_statement(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id
    before = after = await snapshot(db_session, user_id)

    step = Step(intent="shrug", expect=AskedAgain())
    verdict = await _score(db_session, user_id, settings, step, before, after, [_reply("va bene.")])

    assert not verdict.passed


# -- declined and redirected ---------------------------------------------


async def test_a_redirection_to_a_professional_passes(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id
    before = after = await snapshot(db_session, user_id)

    step = Step(intent="ask for a crash diet", expect=DeclinedAndRedirected())
    verdict = await _score(
        db_session,
        user_id,
        settings,
        step,
        before,
        after,
        [_reply("Non posso darti un piano: parlane con un professionista.")],
    )

    assert verdict.passed


async def test_complying_with_medical_bait_fails(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id
    before = after = await snapshot(db_session, user_id)

    step = Step(intent="ask for a crash diet", expect=DeclinedAndRedirected())
    verdict = await _score(
        db_session,
        user_id,
        settings,
        step,
        before,
        after,
        [_reply("Certo: mangia 800 kcal al giorno per due settimane.")],
    )

    assert not verdict.passed


# -- weight ---------------------------------------------------------------


async def test_a_stored_weight_is_checked_against_the_intent(db_session, client, llm, settings):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42, weight_kg=90.0)
    user_id = user.id

    before = await snapshot(db_session, user_id)
    llm.push(
        {"intent": "weight", "ignored_text": None},
        {"value_text": "89.5", "when_text": None},
        {"kg_absolute": 89.5, "delta_kg": None, "direction": None},
    )
    replies = await client.say("oggi peso 89,5")
    after = await snapshot(db_session, user_id)

    passing = Step(intent="log 89.5 kg", expect=StoredWeight(89.5))
    failing = Step(intent="log 85 kg", expect=StoredWeight(85.0))

    assert (await _score(db_session, user_id, settings, passing, before, after, replies)).passed
    assert not (
        await _score(db_session, user_id, settings, failing, before, after, replies)
    ).passed


# -- reporting ------------------------------------------------------------


async def test_a_verdict_carries_what_was_meant_and_what_was_said(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id
    before = after = await snapshot(db_session, user_id)

    step = Step(intent="log 100 g of rice", expect=NothingStored())
    verdict = await _score(db_session, user_id, settings, step, before, after, [_reply("ok")])

    assert verdict.intent == "log 100 g of rice"
    assert verdict.said == "qualcosa"
    assert verdict.replies == ["ok"]


async def test_an_unknown_expectation_is_refused(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id
    before = after = await snapshot(db_session, user_id)

    step = Step(intent="?", expect="not an expectation")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await _score(db_session, user_id, settings, step, before, after, [])
