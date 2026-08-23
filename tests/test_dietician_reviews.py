from __future__ import annotations

import datetime as dt
import re
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from calobot.persistence.models import FoodEntry, Provenance
from calobot.reporting.dietician import (
    DieticianReview,
    build_daily_advice,
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
    review = await build_dietitian_review(mock_gateway, [], TZ_ROME, "week")
    assert review is None


async def test_build_dietitian_review_enforces_minimum_days_requirement():
    mock_gateway = AsyncMock()
    entries = [
        _make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)),
        _make_entry("Pasta", 100, 350, Provenance.tabella, dt.datetime(2026, 8, 17, 13, 0)),
    ]
    # Only 1 unique day logged (Aug 17)
    review = await build_dietitian_review(mock_gateway, entries, TZ_ROME, "week")
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

    review = await build_dietitian_review(mock_gateway, entries, TZ_ROME, "week")
    assert review == expected_review
    mock_gateway.call_structured.assert_called_once()


async def test_build_dietitian_review_uses_rest_of_week_framing_for_week_period():
    mock_gateway = AsyncMock()
    mock_gateway.call_structured.return_value = DieticianReview(
        summary="s", density_insight="d", temporal_pattern_insight="t", sourcing_insight="so", actionable_tip="a"
    )
    entries = [
        _make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)),
        _make_entry("Pasta", 100, 350, Provenance.tabella, dt.datetime(2026, 8, 18, 13, 0)),
        _make_entry("Insalata", 200, 20, Provenance.tabella, dt.datetime(2026, 8, 19, 20, 0)),
    ]

    await build_dietitian_review(mock_gateway, entries, TZ_ROME, "week")

    system_prompt = mock_gateway.call_structured.call_args.kwargs["system_prompt"]
    assert "GIORNI RIMANENTI" in system_prompt
    assert "ABITUDINE GENERALE" not in system_prompt


async def test_build_dietitian_review_uses_general_habit_framing_for_month_and_year_periods():
    mock_gateway = AsyncMock()
    mock_gateway.call_structured.return_value = DieticianReview(
        summary="s", density_insight="d", temporal_pattern_insight="t", sourcing_insight="so", actionable_tip="a"
    )
    entries = [
        _make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)),
        _make_entry("Pasta", 100, 350, Provenance.tabella, dt.datetime(2026, 8, 18, 13, 0)),
        _make_entry("Insalata", 200, 20, Provenance.tabella, dt.datetime(2026, 8, 19, 20, 0)),
    ]

    for period in ("month", "year"):
        mock_gateway.call_structured.reset_mock()
        await build_dietitian_review(mock_gateway, entries, TZ_ROME, period)
        system_prompt = mock_gateway.call_structured.call_args.kwargs["system_prompt"]
        assert "ABITUDINE GENERALE" in system_prompt
        assert "grammi di un macronutriente" in system_prompt
        assert "GIORNI RIMANENTI" not in system_prompt


# Guards against the model stating a specific macronutrient gram amount despite
# instructions (design.md - Risks: "Non inventare dati o macronutrienti"). Matches
# a digit-plus-gram token within a short window of a macronutrient word, in either
# order ("30g di proteine" / "proteine: 30 grammi").
_MACRO_GRAM_CLAIM = re.compile(
    r"(\d+\s*(g|gr|grammi)\b.{0,25}(protein|grass|carboidrat))"
    r"|((protein|grass|carboidrat)\w*.{0,25}\d+\s*(g|gr|grammi)\b)",
    re.IGNORECASE,
)


def test_macro_gram_claim_regex_flags_a_specific_gram_amount():
    assert _MACRO_GRAM_CLAIM.search("Oggi hai mangiato 30g di proteine, ottimo lavoro.")
    assert _MACRO_GRAM_CLAIM.search("Cerca di assumere proteine: 50 grammi al giorno.")


def test_macro_gram_claim_regex_allows_qualitative_advice():
    assert not _MACRO_GRAM_CLAIM.search(
        "Assicurati una fonte proteica ad ogni pasto e alterna carboidrati semplici e complessi."
    )


async def test_general_habit_tip_from_stubbed_output_has_no_macro_gram_claim():
    mock_gateway = AsyncMock()
    mock_gateway.call_structured.return_value = DieticianReview(
        summary="s",
        density_insight="d",
        temporal_pattern_insight="t",
        sourcing_insight="so",
        actionable_tip="Assicurati una fonte proteica ad ogni pasto, variando anche i carboidrati.",
    )
    entries = [
        _make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0)),
        _make_entry("Pasta", 100, 350, Provenance.tabella, dt.datetime(2026, 8, 18, 13, 0)),
        _make_entry("Insalata", 200, 20, Provenance.tabella, dt.datetime(2026, 8, 19, 20, 0)),
    ]

    review = await build_dietitian_review(mock_gateway, entries, TZ_ROME, "month")

    assert not _MACRO_GRAM_CLAIM.search(review.actionable_tip)


async def test_build_daily_advice_returns_none_for_no_entries():
    mock_gateway = AsyncMock()
    advice = await build_daily_advice(mock_gateway, [], remaining_kcal=1500.0, activity_credit_kcal=0.0)
    assert advice is None
    mock_gateway.call_structured.assert_not_called()


async def test_build_daily_advice_returns_text_on_success():
    mock_gateway = AsyncMock()
    from calobot.reporting.dietician import DailyAdvice

    mock_gateway.call_structured.return_value = DailyAdvice(advice="Aggiungi una fonte proteica stasera.")
    entries = [_make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0))]

    advice = await build_daily_advice(mock_gateway, entries, remaining_kcal=500.0, activity_credit_kcal=200.0)

    assert advice == "Aggiungi una fonte proteica stasera."


async def test_build_daily_advice_falls_back_to_none_on_llm_error():
    mock_gateway = AsyncMock()
    mock_gateway.call_structured.side_effect = RuntimeError("boom")
    entries = [_make_entry("Mela", 150, 52, Provenance.tabella, dt.datetime(2026, 8, 17, 10, 0))]

    advice = await build_daily_advice(mock_gateway, entries, remaining_kcal=500.0, activity_credit_kcal=0.0)

    assert advice is None


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


async def test_weekly_report_splits_if_review_is_too_long(db_session, client, llm):
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
    # 3. Dietician structured review with long fields to exceed 1024 characters
    llm.push({
        "summary": "A" * 300,
        "density_insight": "B" * 300,
        "temporal_pattern_insight": "C" * 300,
        "sourcing_insight": "D" * 300,
        "actionable_tip": "E" * 100
    })

    sent = await client.say("mostrami il report di questa settimana")
    
    # It should be split into 2 messages: the photo with the short calorie summary caption,
    # and a separate text message containing the complete, long dietician review.
    assert len(sent) == 2
    
    # Message 0 is the photo with the short caption (calorie summary)
    assert sent[0].has_image is True
    assert "Calorie (week):" in sent[0].text
    assert "IL PARERE DEL NUTRIZIONISTA" not in sent[0].text
    assert len(sent[0].text) < 200

    # Message 1 is the dietician review sent as a separate message
    assert sent[1].has_image is False
    assert "IL PARERE DEL NUTRIZIONISTA" in sent[1].text
    assert "A" * 300 in sent[1].text
    assert "B" * 300 in sent[1].text
    assert "E" * 100 in sent[1].text


