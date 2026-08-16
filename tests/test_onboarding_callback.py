"""Regression tests for a real bug reported from a live conversation: tapping an
onboarding button (sesso/livello di attività/ritmo) never applied the answer to the
profile, because on_answer_callback routed straight into the general message
pipeline regardless of onboarding state, which correctly-but-uselessly classified
the bare button label (e.g. "maschio") as unrelated chat.

Driven through the transport double: the tap carries the real action data through
the real callback handler, and the identifier of the keyboard it came from is a real
message identifier - neither of which a mocked bot could provide.
"""

from __future__ import annotations

from calobot.persistence.models import Sesso
from calobot.persistence.repository import get_user_by_telegram_id


async def _reload(db_session, telegram_user_id: int):
    db_session.expire_all()
    return await get_user_by_telegram_id(db_session, telegram_user_id)


async def test_onboarding_button_answer_is_applied_to_profile(db_session, client):
    await client.start()
    assert "maschio" in client.last.options  # the sesso question, with its keyboard

    sent = await client.tap("maschio")

    user = await _reload(db_session, client.telegram_user_id)
    assert user.sesso == Sesso.maschio

    # It must advance to the *next* onboarding question, not a generic chat reply.
    assert len(sent) == 1
    assert "nato" in sent[0].text.lower() or "età" in sent[0].text.lower()


async def test_stale_button_tap_does_not_corrupt_a_later_field(db_session, client):
    """Tapping an old keyboard from an already-answered question must not force the
    tapped label onto whatever field onboarding has since moved on to."""
    await client.start()
    sesso_question = client.last

    await client.tap("maschio")  # onboarding advances to date of birth

    sent = await client.tap("maschio", on=sesso_question)

    user = await _reload(db_session, client.telegram_user_id)
    assert user.sesso == Sesso.maschio
    assert user.data_nascita is None  # untouched, not corrupted by the stale tap

    # The user is simply shown the step they are actually on.
    assert len(sent) == 1
    assert "nato" in sent[0].text.lower() or "età" in sent[0].text.lower()
