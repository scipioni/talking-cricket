"""End-to-end pipeline tests with a stubbed LLM gateway (no live endpoint available
in this environment - see openspec/changes/calobot-v1/tasks.md group 14). Exercises
the real classify -> extract -> draft -> resolve -> store path through
MessagePipeline, which is what the telegram handlers call in production."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from calobot.ingestion.pipeline import MessagePipeline
from calobot.llm.content import TextContent
from calobot.llm.gateway import LLMGateway
from calobot.persistence.repository import create_user
from calobot.persistence.seed import seed_all
from calobot.profile.service import apply_onboarding_field
from calobot.settings import Settings


def _fake_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
    )


def _stub_gateway(responses: list[dict]) -> LLMGateway:
    settings = Settings(telegram_bot_token="x")  # type: ignore[call-arg]
    gateway = LLMGateway(settings)
    gateway._client.chat.completions.create = AsyncMock(
        side_effect=[_fake_response(r) for r in responses]
    )
    return gateway


async def _full_user(db_session):
    import datetime as dt

    user = await create_user(db_session, telegram_user_id=42)
    await apply_onboarding_field(db_session, user, "sesso", "maschio")
    await apply_onboarding_field(db_session, user, "data_nascita", dt.date(1990, 1, 1))
    await apply_onboarding_field(db_session, user, "altezza_cm", 178.0)
    await apply_onboarding_field(db_session, user, "peso_attuale_kg", 90.0)
    await apply_onboarding_field(db_session, user, "peso_obiettivo_kg", 80.0)
    await apply_onboarding_field(db_session, user, "livello_attivita", "moderato")
    await apply_onboarding_field(db_session, user, "ritmo", "moderato")
    user.onboarding_complete = True
    await db_session.flush()
    return user


async def test_food_with_explicit_grams_resolves_from_table(db_session):
    await seed_all(db_session)
    user = await _full_user(db_session)

    gateway = _stub_gateway(
        [
            {"intent": "food", "ignored_text": None},  # classify
            {  # extract_food
                "items": [
                    {
                        "description": "noci",
                        "quantity_grams": 10,
                        "quantity_count": None,
                        "count_unit_hint": None,
                        "household_measure": None,
                        "preparation": None,
                        "preparation_material_but_unstated": False,
                    }
                ],
                "when_text": None,
            },
            {"selected_candidate_id": 1},  # table row selection -> should match Walnuts row
        ]
    )

    settings = Settings(telegram_bot_token="x")  # type: ignore[call-arg]
    pipeline = MessagePipeline(db_session, gateway, settings, user)
    messages = await pipeline.handle(TextContent(text="ho mangiato 10g di noci"), "ho mangiato 10g di noci")

    assert len(messages) == 1
    assert "noci" in messages[0].text
    assert messages[0].entry_ref is not None
    assert messages[0].entry_ref[0] == "food"


async def test_food_with_vague_portion_asks_then_stores(db_session):
    await seed_all(db_session)
    user = await _full_user(db_session)

    gateway = _stub_gateway(
        [
            {"intent": "food", "ignored_text": None},  # classify
            {  # extract_food: vague portion
                "items": [
                    {
                        "description": "pasta al pesto",
                        "quantity_grams": None,
                        "quantity_count": None,
                        "count_unit_hint": None,
                        "household_measure": "un piatto",
                        "preparation": None,
                        "preparation_material_but_unstated": False,
                    }
                ],
                "when_text": None,
            },
        ]
    )
    settings = Settings(telegram_bot_token="x")  # type: ignore[call-arg]
    pipeline = MessagePipeline(db_session, gateway, settings, user)

    messages = await pipeline.handle(
        TextContent(text="un piatto di pasta al pesto"), "un piatto di pasta al pesto"
    )
    assert len(messages) == 1
    assert messages[0].buttons  # asked for a portion with tappable options

    # user answers with a button label
    gateway._client.chat.completions.create = AsyncMock(
        side_effect=[_fake_response({"selected_candidate_id": None})]  # no table match -> estimate
        + [_fake_response({"kcal_per_100g": 200, "display_name_it": "pasta al pesto"})]
    )
    answer = messages[0].buttons[1]  # "medio (~120g)"
    follow_up = await pipeline.handle(TextContent(text=answer), answer)
    assert len(follow_up) == 1
    assert follow_up[0].entry_ref is not None
    assert "stima" in follow_up[0].text


async def test_weight_message_end_to_end(db_session):
    await seed_all(db_session)
    user = await _full_user(db_session)

    gateway = _stub_gateway(
        [
            {"intent": "weight", "ignored_text": None},
            {"value_text": "89.5", "when_text": None},
            {"kg_absolute": 89.5, "delta_kg": None, "direction": None},
        ]
    )
    settings = Settings(telegram_bot_token="x")  # type: ignore[call-arg]
    pipeline = MessagePipeline(db_session, gateway, settings, user)

    # small, plausible change from the 90kg logged at onboarding -> stored directly
    messages = await pipeline.handle(TextContent(text="oggi peso 89,5"), "oggi peso 89,5")
    assert len(messages) == 1
    assert "89.5" in messages[0].text
    assert messages[0].entry_ref[0] == "weight"


async def test_report_message_end_to_end(db_session):
    await seed_all(db_session)
    user = await _full_user(db_session)

    gateway = _stub_gateway(
        [
            {"intent": "report", "ignored_text": None},
            {"period_text": None, "topic": "food"},
        ]
    )
    settings = Settings(telegram_bot_token="x")  # type: ignore[call-arg]
    pipeline = MessagePipeline(db_session, gateway, settings, user)

    messages = await pipeline.handle(TextContent(text="report di oggi"), "report di oggi")
    assert len(messages) == 1
    assert "dati" in messages[0].text.lower()  # no food logged -> "non ci sono dati"
