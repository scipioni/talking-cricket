"""Conversational profile edits (specs/user-profile - Profile inspection, editing
and deletion; specs/message-ingestion - Classification of inbound messages).

The onboarding conversation used to be the only moment a profile field was ever set;
`/profilo` only displayed it and `/cancellami` destroyed everything. These tests cover
the new path: name a field in conversation, confirm the proposed change (which states
the budget delta), and have it applied through the same validated write path and
safety limits onboarding already uses.
"""

from __future__ import annotations

import datetime as dt

from harness.state import create_onboarded_user
from sqlalchemy import select

from calobot.persistence.models import PendingDraft, User
from calobot.persistence.seed import seed_all
from calobot.profile.service import (
    budget_with_override,
    current_budget,
    current_field_value,
    describe_profile_change,
    format_field_value,
)

# -- current_field_value / format_field_value ------------------------------


async def test_current_field_value_reads_back_in_the_same_form_parse_field_raw_returns(
    db_session,
):
    await create_onboarded_user(db_session, 1)
    user = (await db_session.execute(select(User))).scalars().one()

    assert await current_field_value(db_session, user, "sesso") == "maschio"
    assert await current_field_value(db_session, user, "data_nascita") == dt.date(1990, 1, 1)
    assert await current_field_value(db_session, user, "altezza_cm") == 178.0
    assert await current_field_value(db_session, user, "peso_obiettivo_kg") == 80.0
    assert await current_field_value(db_session, user, "livello_attivita") == "moderato"
    assert await current_field_value(db_session, user, "ritmo") == "moderato"


def test_format_field_value_renders_each_field_type():
    assert format_field_value("data_nascita", dt.date(1972, 5, 16)) == "1972-05-16"
    assert format_field_value("altezza_cm", 178.0) == "178 cm"
    assert format_field_value("peso_obiettivo_kg", 74.0) == "74 kg"
    assert format_field_value("sesso", "femmina") == "femmina"


# -- budget_with_override --------------------------------------------------


async def test_budget_with_override_previews_without_writing(db_session):
    """The point of a preview: it must not mutate anything, since the change has not
    been confirmed yet. Uses a goal equal to the current weight (90 kg, from
    create_onboarded_user) rather than a nearby number: compute_budget's deficit
    magnitude comes from ritmo, not from how far the goal is, so only a goal that
    crosses into maintenance is guaranteed to move the target."""
    await create_onboarded_user(db_session, 2)
    user = (await db_session.execute(select(User))).scalars().one()

    before = await current_budget(db_session, user)
    previewed = await budget_with_override(db_session, user, "peso_obiettivo_kg", 90.0)

    assert previewed is not None
    assert previewed.direction == "maintenance"
    assert previewed.target_kcal != before.target_kcal

    db_session.expire_all()
    unchanged = (await db_session.execute(select(User))).scalars().one()
    assert unchanged.peso_obiettivo_kg == 80.0  # the stored goal, from create_onboarded_user


async def test_budget_with_override_is_none_when_the_rest_of_the_profile_is_incomplete(
    db_session,
):
    from calobot.persistence.repository import create_user

    user = await create_user(db_session, telegram_user_id=3)
    assert await budget_with_override(db_session, user, "peso_obiettivo_kg", 74.0) is None


# -- describe_profile_change ------------------------------------------------


async def test_describe_profile_change_states_old_new_and_budget_delta(db_session):
    await create_onboarded_user(db_session, 4)
    user = (await db_session.execute(select(User))).scalars().one()

    text = await describe_profile_change(db_session, user, "peso_obiettivo_kg", 90.0)

    assert "80 kg" in text  # the current value
    assert "90 kg" in text  # the proposed value
    assert "budget" in text.lower()


async def test_describe_profile_change_omits_the_budget_line_when_it_does_not_move(
    db_session,
):
    """peso_obiettivo_kg=80 is already the stored goal (create_onboarded_user sets it
    to weight_kg - 10 = 80): no change to preview, so there is nothing to compare."""
    await create_onboarded_user(db_session, 5)
    user = (await db_session.execute(select(User))).scalars().one()

    text = await describe_profile_change(db_session, user, "peso_obiettivo_kg", 80.0)

    assert "budget" not in text.lower()


# -- end to end --------------------------------------------------------------


async def test_a_profile_edit_asks_for_confirmation_and_states_the_budget_delta(
    db_session, client, llm
):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "profile", "ignored_text": None},
        {"field": "peso_obiettivo_kg", "value_text": "90kg"},
    )

    sent = await client.say("ora il mio peso obiettivo è 90kg")

    assert "80 kg" in sent[0].text
    assert "90 kg" in sent[0].text
    assert "budget" in sent[0].text.lower()
    assert sent[0].labels[:2] == ["sì", "no"]

    db_session.expire_all()
    user = (await db_session.execute(select(User))).scalars().one()
    assert user.peso_obiettivo_kg == 80.0  # unchanged - nothing applied until confirmed


async def test_confirming_applies_the_change_and_profilo_reflects_it(db_session, client, llm):
    from calobot.profile.service import format_profile_summary

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "profile", "ignored_text": None},
        {"field": "peso_obiettivo_kg", "value_text": "74kg"},
    )
    asked = await client.say("ora il mio peso obiettivo è 74kg")

    confirmed = await client.tap(asked[0].labels[0])  # "sì"

    assert "74" in confirmed[0].text
    db_session.expire_all()
    user = (await db_session.execute(select(User))).scalars().one()
    assert user.peso_obiettivo_kg == 74.0
    assert list((await db_session.execute(select(PendingDraft))).scalars()) == []

    summary = await format_profile_summary(db_session, user)
    assert "74.0 kg" in summary


async def test_declining_leaves_the_profile_untouched(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "profile", "ignored_text": None},
        {"field": "peso_obiettivo_kg", "value_text": "74kg"},
    )
    asked = await client.say("ora il mio peso obiettivo è 74kg")

    declined = await client.tap(asked[0].labels[1])  # "no"

    assert "non ho cambiato" in declined[0].text.lower()
    db_session.expire_all()
    user = (await db_session.execute(select(User))).scalars().one()
    assert user.peso_obiettivo_kg == 80.0
    assert list((await db_session.execute(select(PendingDraft))).scalars()) == []


async def test_a_birth_date_edit_resolves_to_the_stated_date(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "profile", "ignored_text": None},
        {"field": "data_nascita", "value_text": "16/5/72"},
    )
    asked = await client.say("la mia data di nascita è 16/5/72")
    assert "1972-05-16" in asked[0].text

    await client.tap(asked[0].labels[0])

    db_session.expire_all()
    user = (await db_session.execute(select(User))).scalars().one()
    assert user.data_nascita == dt.date(1972, 5, 16)


async def test_an_unsafe_goal_weight_is_refused_without_a_confirmation_step(
    db_session, client, llm
):
    """The safety check runs before a confirmation is even offered - design.md: never
    confirm a change that will be refused anyway."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "profile", "ignored_text": None},
        {"field": "peso_obiettivo_kg", "value_text": "45kg"},  # BMI < 18.5 at 178cm
    )

    sent = await client.say("il mio peso obiettivo è 45kg")

    assert "indice di massa corporea" in sent[0].text
    assert not sent[0].options  # refused outright, not offered as a choice
    db_session.expire_all()
    user = (await db_session.execute(select(User))).scalars().one()
    assert user.peso_obiettivo_kg == 80.0
    assert list((await db_session.execute(select(PendingDraft))).scalars()) == []


async def test_an_unparseable_value_is_asked_again_then_gives_up(db_session, client, llm, settings):
    """Bounded the same way as the food/activity clarification loop
    (clarification_attempt_limit): no gateway call is made on a retry here, since the
    profile draft is resolved deterministically via parse_field_raw, not extraction."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "profile", "ignored_text": None},
        {"field": "data_nascita", "value_text": "boh"},
    )
    first = await client.say("cambio la mia data di nascita")
    assert first[0].options

    for _ in range(settings.clarification_attempt_limit - 1):
        await client.say("boh")

    final = await client.say("boh")

    assert "lasciamo perdere" in final[-1].text.lower()
    db_session.expire_all()
    assert list((await db_session.execute(select(PendingDraft))).scalars()) == []
    user = (await db_session.execute(select(User))).scalars().one()
    assert user.data_nascita == dt.date(1990, 1, 1)  # unchanged


async def test_current_weight_is_still_a_measurement_not_a_profile_edit(db_session, client, llm):
    """Regression: peso_attuale_kg is not settable on this path (design.md - Current
    weight is not settable on this path). A body-weight statement must classify as
    weight and open no profile draft."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "weight", "ignored_text": None},
        {"value_text": "89.5 kg", "when_text": None},
        {"kg_absolute": 89.5, "delta_kg": None, "direction": None},
    )

    sent = await client.say("peso 89.5 kg")

    assert "peso registrato" in sent[0].text.lower()
    db_session.expire_all()
    assert list((await db_session.execute(select(PendingDraft))).scalars()) == []
