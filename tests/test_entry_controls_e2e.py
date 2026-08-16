"""Entry controls and correction-by-reply, driven end to end.

These paths live entirely in the handler layer - above MessagePipeline - and had no
coverage before the transport double, because reaching them needs real message
identifiers and real inline keyboards.
"""

from __future__ import annotations

from harness.state import create_onboarded_user, food_extraction
from sqlalchemy import select

from calobot.persistence.models import FoodEntry
from calobot.persistence.seed import seed_all


async def _log(client, llm, description: str, grams: int):
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description=description, quantity_grams=grams),
        {"selected_candidate_id": None},
        {"kcal_per_100g": 100, "display_name_it": description},
    )
    sent = await client.say(f"ho mangiato {grams}g di {description}")
    return sent[-1]


async def _entries(db_session) -> list[FoodEntry]:
    db_session.expire_all()
    result = await db_session.execute(select(FoodEntry).order_by(FoodEntry.id))
    return list(result.scalars())


async def test_reply_to_a_confirmation_corrects_that_entry_not_the_latest(
    db_session, client, llm
):
    """Deterministic targeting: the reply names the entry through its confirmation
    message. This can only work if the identifier stored against the entry is the
    identifier of the message that was actually sent."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    first = await _log(client, llm, "riso", 100)
    await _log(client, llm, "pollo", 200)

    sent = await client.reply_to(first, "no erano 20g")

    assert "Corretto" in sent[-1].text

    riso, pollo = await _entries(db_session)
    assert riso.grams == 20  # the entry that was replied to
    assert pollo.grams == 200  # the most recent one, untouched


async def test_delete_control_soft_deletes_and_removes_from_reports(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    confirmation = await _log(client, llm, "riso", 100)
    assert "🗑 elimina" in confirmation.options

    await client.tap("🗑 elimina", on=confirmation)

    entry = (await _entries(db_session))[0]
    assert entry.deleted_at is not None  # soft-deleted, not removed

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "food"},
    )
    sent = await client.say("report di oggi")

    assert "non ci sono dati" in sent[-1].text.lower()


async def test_modify_control_explains_how_to_correct(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    confirmation = await _log(client, llm, "riso", 100)

    sent = await client.tap("✏️ modifica", on=confirmation)

    assert "rispondi" in sent[-1].text.lower()
