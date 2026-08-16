"""Tests for the transport double itself (specs/test-transport).

These assert that the harness is faithful in the ways the rest of the suite relies
on. If any of these break, every test built on the double is suspect - the double is
tested before it is trusted.
"""

from __future__ import annotations

import pytest
from aiogram.methods import BanChatMember
from harness.client import ScenarioError
from harness.state import create_onboarded_user, food_extraction
from harness.transport import UnsupportedApiCall
from sqlalchemy import select

from calobot.persistence.models import FoodEntry
from calobot.persistence.seed import seed_all


async def _log_walnuts(client, llm):
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(),
        {"selected_candidate_id": 1},
    )
    return await client.say("ho mangiato 10g di noci")


# -- identity -------------------------------------------------------------


async def test_confirmation_identifier_is_the_identifier_of_the_message_sent(
    db_session, client, llm
):
    """The link that makes correction-by-reply work: production stores the id the
    send returned. With a mocked bot this is a mock object and the whole path is
    exercised in name only."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    sent = await _log_walnuts(client, llm)
    confirmation = sent[-1]

    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert isinstance(entry.confirmation_message_id, int)
    assert entry.confirmation_message_id == confirmation.message_id


async def test_message_identifiers_are_distinct(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    await _log_walnuts(client, llm)
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="mela", quantity_grams=150),
        {"selected_candidate_id": None},
        {"kcal_per_100g": 52, "display_name_it": "mela"},
    )
    await client.say("una mela da 150g")

    ids = [m.message_id for m in client.inbox]
    assert len(ids) == len(set(ids))


# -- transcript -----------------------------------------------------------


async def test_controls_swapped_after_sending_are_reflected_on_that_message(
    db_session, client, llm
):
    """A confirmation is sent with no keyboard and then has entry controls attached
    to it. The transcript must show what the user is looking at now."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    sent = await _log_walnuts(client, llm)
    confirmation = sent[-1]

    assert set(confirmation.labels) == {"✏️ modifica", "🗑 elimina"}
    assert confirmation.options["🗑 elimina"].startswith("entry:elimina:food:")


async def test_chart_reply_records_an_image_and_keeps_its_caption(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    await _log_walnuts(client, llm)

    # A chart is rendered for periods wider than a single day.
    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": "settimana", "topic": "food"},
    )
    sent = await client.say("report della settimana")

    assert sent[-1].has_image
    assert sent[-1].text  # the caption survives without the image being decoded


async def test_typing_indicator_covers_a_processed_message(db_session, client, llm, fake_bot):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    await _log_walnuts(client, llm)

    assert fake_bot.chat_actions == ["typing"]


# -- options --------------------------------------------------------------


async def test_tap_on_a_label_that_was_never_offered_is_a_scenario_error(db_session, client):
    await client.start()

    with pytest.raises(ScenarioError, match="mai offerto|never|non esiste|offers"):
        await client.tap("un'opzione inventata")


async def test_tap_by_label_sends_the_action_data_a_real_client_would_send(db_session, client):
    await client.start()
    origin = client.last

    assert origin.options["maschio"] == "ans:maschio"

    await client.tap("maschio")
    # Routed through the real answer-callback handler, which acknowledges the tap.
    assert client.bot.answered_callbacks == [None]


async def test_tap_on_a_superseded_keyboard_is_delivered_faithfully(db_session, client):
    """A stale tap is a thing users really do, and one of the adversary's tools. The
    double must deliver it as Telegram would, so that the bot's own handling of it is
    what the test observes."""
    await client.start()
    stale = client.last  # the sesso question

    await client.tap("maschio")  # onboarding moves on to date of birth

    replies = await client.tap("maschio", on=stale)

    # Delivered, not rejected: the bot answered rather than the harness refusing.
    assert replies
    assert client.bot.answered_callbacks == [None, None]


# -- photos ---------------------------------------------------------------


async def test_photo_is_delivered_through_the_photo_handler(db_session, client):
    """The handler fetches the largest offered size and downloads it, so the double
    has to serve the get-file / download-file pair, not just carry the update."""
    await create_onboarded_user(db_session, 42)

    sent = await client.send_photo(b"fake-jpeg-bytes", caption="pasta")

    # v1's placeholder reply - replaced by calobot-photo-input, and asserted here
    # only to prove the photo reached the handler at all.
    assert "foto" in sent[-1].text.lower()


async def test_photo_without_a_registered_user_stores_nothing(db_session, client):
    sent = await client.send_photo(b"fake-jpeg-bytes")

    assert "/start" in sent[-1].text


# -- fidelity boundary ----------------------------------------------------


async def test_a_method_outside_the_boundary_is_refused_not_faked(fake_bot):
    with pytest.raises(UnsupportedApiCall, match="BanChatMember"):
        await fake_bot(BanChatMember(chat_id=1, user_id=2))
