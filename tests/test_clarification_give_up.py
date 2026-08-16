"""The clarification loop gives up (specs/message-ingestion - Draft completeness and
the clarification loop).

The defect, from run 2 of `marco-three-days`:

    BOT   Quanto pesava la porzione di riso?
    USER  eh boh, tipo medio credo?
    BOT   Non ho capito. Quanto pesava la porzione di riso?
    USER  eh boh, non ricordo
    BOT   Non ho capito. Quanto pesava la porzione di riso?
    USER  eh?
    BOT   Non ho capito. Quanto pesava la porzione di riso?

No attempt counter, so the only exit was draft expiry - a timer the user cannot see,
predict or be told about.
"""

from __future__ import annotations

import pytest
from harness.run import DEFAULT_PROGRESS_LIMIT
from harness.state import create_onboarded_user, food_extraction
from sqlalchemy import select

from calobot.ingestion import drafts
from calobot.ingestion.pipeline import _REASK_PREFIXES, ABANDON_OPTION, _reask_prefix
from calobot.persistence.models import FoodEntry, PendingDraft
from calobot.persistence.seed import seed_all
from calobot.settings import Settings


async def _ask_for_a_portion(client, llm, description="riso"):
    """Get the bot into a state where it is asking for a portion."""
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description=description, quantity_grams=None, household_measure="un piatto"),
    )
    return await client.say(f"ho mangiato un piatto di {description}")


def _shrug(llm):
    """An unusable answer: classified as conversation, so the draft is not replaced."""
    llm.push({"intent": "other", "ignored_text": None})


async def _entries(db_session):
    db_session.expire_all()
    return list((await db_session.execute(select(FoodEntry))).scalars())


async def _draft(db_session, user_id):
    db_session.expire_all()
    result = await db_session.execute(select(PendingDraft).where(PendingDraft.user_id == user_id))
    return result.scalar_one_or_none()


# -- counting -------------------------------------------------------------


async def test_the_attempt_count_persists_with_the_draft(db_session, client, llm):
    """Task 1.4: a stalled conversation survives a restart with its count intact,
    because the count lives in the draft payload the draft already persists."""
    await seed_all(db_session)
    user_id = (await create_onboarded_user(db_session, 42)).id

    await _ask_for_a_portion(client, llm)
    _shrug(llm)
    await client.say("boh")

    draft = await _draft(db_session, user_id)
    assert drafts.attempts(draft) == 1


async def test_a_draft_written_before_this_existed_reads_as_zero(db_session, client, llm):
    await seed_all(db_session)
    user_id = (await create_onboarded_user(db_session, 42)).id
    await _ask_for_a_portion(client, llm)

    draft = await _draft(db_session, user_id)
    assert "attempts" not in draft.payload
    assert drafts.attempts(draft) == 0


async def test_answering_resets_the_count(db_session, client, llm):
    """Task 1.5: the bound is on consecutive failures for one question, not on the
    conversation as a whole."""
    await seed_all(db_session)
    user_id = (await create_onboarded_user(db_session, 42)).id

    asked = await _ask_for_a_portion(client, llm)
    _shrug(llm)
    await client.say("boh")
    assert drafts.attempts(await _draft(db_session, user_id)) == 1

    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 130, "display_name_it": "riso"},
    )
    await client.tap(asked[-1].labels[1])

    # Draft completed and discarded, so nothing carries over.
    assert await _draft(db_session, user_id) is None
    assert len(await _entries(db_session)) == 1


# -- giving up ------------------------------------------------------------


async def test_three_unusable_answers_end_the_conversation(db_session, client, llm, settings):
    """Task 2.5: the exchange from the live run, which used to repeat forever."""
    await seed_all(db_session)
    user_id = (await create_onboarded_user(db_session, 42)).id
    assert settings.clarification_attempt_limit == 3

    await _ask_for_a_portion(client, llm)
    for _ in range(settings.clarification_attempt_limit - 1):
        _shrug(llm)
        replies = await client.say("boh")
        assert replies[-1].options, "still asking, correctly"

    _shrug(llm)
    final = await client.say("eh?")

    assert not final[-1].options, "the bot should have stopped asking"
    assert "riso" in final[-1].text, "the give-up must name what was dropped"
    assert await _draft(db_session, user_id) is None
    assert await _entries(db_session) == []


async def test_giving_up_never_invents_the_missing_value(db_session, client, llm, settings):
    """Task 2.4: a wrong quantity the user never confirmed is exactly the corruption
    the clarification loop exists to prevent."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    await _ask_for_a_portion(client, llm)
    for _ in range(settings.clarification_attempt_limit):
        _shrug(llm)
        await client.say("boh")

    assert await _entries(db_session) == []


async def test_a_zero_quantity_is_bounded_by_the_same_loop(db_session, client, llm, settings):
    """Task 2.6: since calobot-false-confirmation a zero resolves as unresolved, which
    is a second route into this loop. It must be bounded too."""
    await seed_all(db_session)
    user_id = (await create_onboarded_user(db_session, 42)).id

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="cena", quantity_grams=0),
    )
    asked = await client.say("registra 0 calorie per la cena")
    assert asked[-1].options

    for _ in range(settings.clarification_attempt_limit):
        _shrug(llm)
        final = await client.say("boh")

    assert not final[-1].options
    assert await _draft(db_session, user_id) is None
    assert await _entries(db_session) == []


# -- wording --------------------------------------------------------------


async def test_consecutive_asks_are_worded_differently(db_session, client, llm, settings):
    """Task 3.5: a user who did not understand the question is shown a different one -
    the only chance the second attempt has of doing better than the first."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    await _ask_for_a_portion(client, llm)

    asks = []
    for _ in range(settings.clarification_attempt_limit - 1):
        _shrug(llm)
        asks.append((await client.say("boh"))[-1].text)

    assert len(set(asks)) == len(asks), f"repeated wording: {asks}"


def test_the_rotation_cannot_run_out_before_the_limit():
    """Task 3.6: asserted rather than commented, so raising the limit without adding
    wording fails here instead of silently repeating the last phrasing."""
    limit = Settings(telegram_bot_token="x").clarification_attempt_limit  # type: ignore[call-arg]

    assert len(_REASK_PREFIXES) >= limit - 1, (
        f"{limit - 1} re-asks happen before give-up but only "
        f"{len(_REASK_PREFIXES)} phrasings exist"
    )


def test_the_prefix_is_clamped_rather_than_wrapping():
    assert _reask_prefix(1) == _REASK_PREFIXES[0]
    assert _reask_prefix(len(_REASK_PREFIXES)) == _REASK_PREFIXES[-1]
    assert _reask_prefix(len(_REASK_PREFIXES) + 5) == _REASK_PREFIXES[-1]


# -- the visible way out --------------------------------------------------


async def test_the_way_out_is_offered_with_every_clarification(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    asked = await _ask_for_a_portion(client, llm)

    assert ABANDON_OPTION in asked[-1].labels


async def test_abandoning_leaves_no_entry_and_no_open_draft(db_session, client, llm):
    """Task 4.4. Tapped by label, so the option really is reachable from the keyboard
    the user is looking at."""
    await seed_all(db_session)
    user_id = (await create_onboarded_user(db_session, 42)).id

    await _ask_for_a_portion(client, llm)
    replies = await client.tap(ABANDON_OPTION)

    assert await _draft(db_session, user_id) is None
    assert await _entries(db_session) == []
    assert "non ho registrato" in replies[-1].text.lower()


async def test_abandoning_costs_no_model_call(db_session, client, llm):
    """It is matched before the answer is parsed or re-classified, so a user backing
    out does not pay for a round trip."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    await _ask_for_a_portion(client, llm)
    before = len(llm.calls)

    await client.tap(ABANDON_OPTION)

    assert len(llm.calls) == before


@pytest.mark.parametrize(
    "answer", ["150", "150 grammi", "medio (~120g)", "piccolo (~80g)", "un piatto", "boh"]
)
def test_the_sentinel_is_not_a_plausible_answer(answer):
    """Task 4.5: it can never be confused with something a user would type as a
    portion, which is why matching it before parsing is safe."""
    assert answer != ABANDON_OPTION


# -- the cross-boundary constraint ----------------------------------------


def test_the_production_limit_is_not_looser_than_the_harness_bound():
    """Task 5.4. If the bot were allowed more attempts than the simulation harness
    tolerates, correct give-up behaviour would fail every run with a false
    no-progress finding. Pinned here so neither value can be changed alone."""
    limit = Settings(telegram_bot_token="x").clarification_attempt_limit  # type: ignore[call-arg]

    assert limit <= DEFAULT_PROGRESS_LIMIT, (
        f"the bot gives up after {limit} attempts but the harness reports a stall "
        f"after {DEFAULT_PROGRESS_LIMIT}: correct behaviour would be reported as a bug"
    )
