from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from calobot.persistence.models import FoodEntry, Provenance
from calobot.reporting.dietician import (
    DieticianReview,
    build_dietitian_review,
    get_dietician_signals,
)

TZ_ROME = ZoneInfo("Europe/Rome")


def _make_entry(
    description: str,
    grams: float,
    kcal_per_100g: float,
    provenance: Provenance,
    local_time: dt.datetime,
) -> FoodEntry:
    # Ensure it's timezone-aware in Europe/Rome
    aware_dt = local_time.replace(tzinfo=TZ_ROME)
    return FoodEntry(
        user_id=1,
        description=description,
        grams=grams,
        kcal_per_100g=kcal_per_100g,
        kcal=round(grams * kcal_per_100g / 100, 1),
        provenance=provenance,
        consumed_at=aware_dt,
    )


def test_get_dietician_signals_computes_correct_nutritional_metrics():
    # Setup test food entries
    entries = [
        # High density snack in the evening
        _make_entry(
            description="Cioccolato fondente",
            grams=30,
            kcal_per_100g=550.0,
            provenance=Provenance.etichetta,
            local_time=dt.datetime(2026, 8, 17, 20, 15),
        ),
        # Low density food in the afternoon
        _make_entry(
            description="Mela",
            grams=150,
            kcal_per_100g=52.0,
            provenance=Provenance.off,
            local_time=dt.datetime(2026, 8, 17, 16, 30),
        ),
        # Medium density food in the morning
        _make_entry(
            description="Yogurt greco",
            grams=150,
            kcal_per_100g=120.0,
            provenance=Provenance.tabella,
            local_time=dt.datetime(2026, 8, 18, 8, 45),
        ),
        # Estimations at late night
        _make_entry(
            description="Pizza",
            grams=300,
            kcal_per_100g=250.0,
            provenance=Provenance.llm,
            local_time=dt.datetime(2026, 8, 19, 23, 10),
        ),
    ]

    signals = get_dietician_signals(entries, TZ_ROME)

    # 1. Calorie summation check
    # Cioccolato: 30 * 5.5 = 165
    # Mela: 150 * 0.52 = 78
    # Yogurt: 150 * 1.2 = 180
    # Pizza: 300 * 2.5 = 750
    # Total: 165 + 78 + 180 + 750 = 1173 kcal
    assert signals["total_kcal"] == 1173
    assert signals["days_logged"] == 3

    # 2. Average density
    # 1173 kcal / 630 grams * 100 = 186.19
    assert signals["average_kcal_density_per_100g"] == 186.2

    # 3. Density groupings
    assert "Cioccolato fondente" in signals["high_density_items"]
    assert "Mela" in signals["low_density_items"]
    assert "Pizza" not in signals["high_density_items"]
    assert "Pizza" not in signals["low_density_items"]

    # 4. Temporal meal time groupings
    # mattina: Yogurt (180 kcal)
    # pomeriggio: Mela (78 kcal)
    # sera: Cioccolato (165 kcal)
    # notte: Pizza (750 kcal)
    assert signals["time_distribution_kcal"]["mattina (05:00-11:59)"] == 180
    assert signals["time_distribution_kcal"]["pomeriggio (12:00-17:59)"] == 78
    assert signals["time_distribution_kcal"]["sera (18:00-21:59)"] == 165
    assert signals["time_distribution_kcal"]["notte (22:00-04:59)"] == 750

    # 5. Sourcing counts
    assert signals["provenance_distribution_count"]["etichetta (foto etichetta)"] == 1
    assert signals["provenance_distribution_count"]["off (barcode)"] == 1
    assert signals["provenance_distribution_count"]["tabella (fct)"] == 1
    assert signals["provenance_distribution_count"]["llm (stima)"] == 1

    # 6. Variety
    assert signals["unique_foods_count"] == 4
    assert signals["frequent_foods"] == ["cioccolato fondente", "mela", "yogurt greco", "pizza"]


async def test_build_dietitian_review_returns_none_for_empty_entries():
    mock_gateway = AsyncMock()
    review = await build_dietitian_review(mock_gateway, [], TZ_ROME)
    assert review is None


async def test_build_dietitian_review_enforces_minimum_days_requirement():
    mock_gateway = AsyncMock()
    entries = [
        _make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)),
        _make_entry("Pasta", 100, 350, Provenance.tabella, dt.datetime(2026, 8, 17, 13, 0)),
    ]
    # Only 1 unique day logged (Aug 17)
    review = await build_dietitian_review(mock_gateway, entries, TZ_ROME)
    assert "Per darti un parere nutrizionale personalizzato" in review
    mock_gateway.call_structured.assert_not_called()


async def test_build_dietitian_review_calls_gateway_successfully():
    mock_gateway = AsyncMock()
    expected_review = DieticianReview(
        summary="Ottimo lavoro di tracciamento!",
        density_insight="I tuoi pasti hanno una densità equilibrata.",
        temporal_pattern_insight="Gli orari dei pasti sono regolari.",
        sourcing_insight="Hai usato ottime fonti precise.",
        actionable_tip="Continua così!",
    )
    mock_gateway.call_structured.return_value = expected_review

    entries = [
        _make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)),
        _make_entry("Pasta", 100, 350, Provenance.tabella, dt.datetime(2026, 8, 18, 13, 0)),
        _make_entry("Insalata", 200, 20, Provenance.tabella, dt.datetime(2026, 8, 19, 20, 0)),
    ]

    review = await build_dietitian_review(mock_gateway, entries, TZ_ROME)
    assert review == expected_review
    mock_gateway.call_structured.assert_called_once()


async def test_weekly_report_triggers_dietician_review(db_session, client, llm):
    from harness.state import create_onboarded_user

    from calobot.persistence.seed import seed_all

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    # Add entries on 3 distinct days: Aug 17, 18, 19
    db_session.add(_make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)))
    db_session.add(_make_entry("Pasta", 100, 350, Provenance.tabella, dt.datetime(2026, 8, 18, 13, 0)))
    db_session.add(_make_entry("Insalata", 200, 20, Provenance.tabella, dt.datetime(2026, 8, 19, 20, 0)))
    await db_session.flush()

    # Script LLM responses:
    # 1. Classification
    llm.push({"intent": "report", "ignored_text": None})
    # 2. Report extraction
    llm.push({"period_text": "questa settimana", "topic": "food"})
    # 3. Dietician structured review
    llm.push({
        "summary": "Bravo!",
        "density_insight": "Ottimo volume.",
        "temporal_pattern_insight": "Timing regolare.",
        "sourcing_insight": "Daily accurato.",
        "actionable_tip": "Continua così!"
    })

    sent = await client.say("mostrami il report di questa settimana")
    assert len(sent) == 1
    text = sent[0].text
    assert "IL PARERE DEL NUTRIZIONISTA" in text
    assert "Andamento generale:* Bravo!" in text
    assert "Sazietà e Volume:* Ottimo volume." in text
    assert "consiglio di questa settimana" in text.lower()
    assert "Continua così!" in text


async def test_weekly_report_with_insufficient_days_bypasses_llm_with_warning(db_session, client, llm):
    from harness.state import create_onboarded_user

    from calobot.persistence.seed import seed_all

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    # Only 1 day logged (Aug 17)
    db_session.add(_make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)))
    await db_session.flush()

    # Script LLM:
    # 1. Classification
    llm.push({"intent": "report", "ignored_text": None})
    # 2. Only report extraction, NO dietician review push (should bypass LLM)
    llm.push({"period_text": "questa settimana", "topic": "food"})

    sent = await client.say("mostrami il report di questa settimana")
    assert len(sent) == 1
    text = sent[0].text
    assert "IL PARERE DEL NUTRIZIONISTA" in text
    assert "Per darti un parere nutrizionale personalizzato" in text


async def test_single_day_report_bypasses_dietician_completely(db_session, client, llm):
    from harness.state import create_onboarded_user

    from calobot.persistence.seed import seed_all

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    # Add entries on 3 distinct days: Aug 17, 18, 19
    db_session.add(_make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)))
    db_session.add(_make_entry("Pasta", 100, 350, Provenance.tabella, dt.datetime(2026, 8, 18, 13, 0)))
    db_session.add(_make_entry("Insalata", 200, 20, Provenance.tabella, dt.datetime(2026, 8, 19, 20, 0)))
    await db_session.flush()

    # Script LLM:
    # 1. Classification
    llm.push({"intent": "report", "ignored_text": None})
    # 2. Only report extraction for today (single day)
    llm.push({"period_text": "oggi", "topic": "food"})

    sent = await client.say("mostrami il report di oggi")
    assert len(sent) == 1
    text = sent[0].text
    assert "IL PARERE DEL NUTRIZIONISTA" not in text

