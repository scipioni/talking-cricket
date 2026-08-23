"""Direct tests of the advice agent's read-only tool registry (tasks.md 3.9, 3.10).
No LLM call is involved here - these test the deterministic handlers wrapped by
`build_tool_registry`, seeded against a real in-memory session."""

from __future__ import annotations

import datetime as dt

from harness.state import create_onboarded_user

from calobot.advice.tools import DateRangeQuery, NoArgs, PeriodQuery, RecentDaysQuery, build_tool_registry
from calobot.persistence.models import ActivityEntry, FoodEntry, Provenance
from calobot.persistence.seed import seed_all


def _make_entry(user_id: int, description: str, grams: float, kcal_per_100g: float, when: dt.datetime):
    return FoodEntry(
        user_id=user_id,
        description=description,
        grams=grams,
        kcal_per_100g=kcal_per_100g,
        kcal=kcal_per_100g * grams / 100.0,
        provenance=Provenance.tabella,
        consumed_at=when,
    )


def _make_activity(user_id: int, kcal: float, when: dt.datetime):
    return ActivityEntry(
        user_id=user_id,
        activity="camminata",
        duration_minutes=60,
        met=4.0,
        kcal=kcal,
        provenance=Provenance.tabella,
        performed_at=when,
    )


async def _registry(db_session, gateway, tz, user):
    tools = await build_tool_registry(db_session, gateway, user, tz)
    return {tool.name: tool for tool in tools}


async def test_calorie_summary_reports_totals_matching_the_report_path(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    today = dt.datetime(2026, 8, 17, 12, 0, tzinfo=dt.UTC)
    db_session.add(_make_entry(user.id, "mela", 150, 52, today))
    await db_session.flush()

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["get_calorie_summary"].handler(
        PeriodQuery(period="day", reference_day=dt.date(2026, 8, 17))
    )

    assert result["no_data"] is False
    assert result["total_kcal"] == round(52 * 150 / 100.0)


async def test_calorie_summary_day_period_includes_activity_credit(db_session, settings, llm):
    from calobot.persistence.timeutil import today_in_timezone
    from calobot.profile.service import current_budget

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    today = today_in_timezone(settings.timezone)
    today_dt = dt.datetime.combine(today, dt.time(12, 0), tzinfo=dt.UTC)
    db_session.add(_make_entry(user.id, "mela", 150, 52, today_dt))
    db_session.add(_make_activity(user.id, 800.0, today_dt))
    await db_session.flush()

    budget = await current_budget(db_session, user)
    expected_credit = min(0.5 * 800.0, 600.0)

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    day_result = await tools["get_calorie_summary"].handler(PeriodQuery(period="day", reference_day=today))
    week_result = await tools["get_calorie_summary"].handler(PeriodQuery(period="week", reference_day=today))

    assert day_result["no_data"] is False
    assert day_result["difference_kcal"] == round(78.0 - (budget.target_kcal + expected_credit))
    # Week period is unaffected by the day's logged activity.
    assert week_result["difference_kcal"] == round(78.0 - budget.target_kcal)


async def test_calorie_summary_reports_no_data_for_an_empty_period(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["get_calorie_summary"].handler(
        PeriodQuery(period="day", reference_day=dt.date(2020, 1, 1))
    )

    assert result["no_data"] is True
    assert result["reference_day"] == "2020-01-01"


async def test_weight_summary_reports_no_data_when_nothing_logged(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["get_weight_summary"].handler(
        PeriodQuery(period="week", reference_day=dt.date(2020, 1, 1))
    )

    assert result["no_data"] is True


async def test_dietician_review_rejects_a_period_shorter_than_a_week(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["get_dietician_review"].handler(PeriodQuery(period="day"))

    assert result["no_data"] is True
    assert "settimana" in result["reason"]


async def test_list_food_entries_returns_compact_facts(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    db_session.add(
        _make_entry(user.id, "mela", 150, 52, dt.datetime(2026, 8, 17, 15, 0, tzinfo=dt.UTC))
    )
    await db_session.flush()

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["list_food_entries"].handler(
        DateRangeQuery(start_day=dt.date(2026, 8, 17), end_day=dt.date(2026, 8, 17))
    )

    assert result["no_data"] is False
    assert result["entries"][0]["description"] == "mela"
    assert result["entries"][0]["grams"] == 150


async def test_list_food_entries_reports_no_data_for_an_empty_range(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["list_food_entries"].handler(
        DateRangeQuery(start_day=dt.date(2020, 1, 1), end_day=dt.date(2020, 1, 2))
    )

    assert result["no_data"] is True


async def test_profile_and_budget_reports_the_current_budget(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["get_profile_and_budget"].handler(NoArgs())

    assert result["no_data"] is False
    assert result["daily_budget_kcal"] > 0
    assert result["goal_kg"] == user.peso_obiettivo_kg


async def test_profile_and_budget_remaining_kcal_includes_activity_credit(db_session, settings, llm):
    from calobot.persistence.timeutil import today_in_timezone
    from calobot.profile.service import current_budget

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    today = today_in_timezone(settings.timezone)
    today_dt = dt.datetime.combine(today, dt.time(12, 0), tzinfo=dt.UTC)
    db_session.add(_make_entry(user.id, "mela", 150, 52, today_dt))
    db_session.add(_make_activity(user.id, 800.0, today_dt))
    await db_session.flush()

    budget = await current_budget(db_session, user)
    expected_credit = min(0.5 * 800.0, 600.0)

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["get_profile_and_budget"].handler(NoArgs())

    assert result["no_data"] is False
    assert result["eaten_today_kcal"] == 78
    assert result["remaining_today_kcal"] == round(budget.target_kcal + expected_credit - 78.0)


def test_recent_days_query_rejects_out_of_range_values():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RecentDaysQuery(days=0)
    with pytest.raises(ValidationError):
        RecentDaysQuery(days=6)
    assert RecentDaysQuery(days=1).days == 1
    assert RecentDaysQuery().days == 2


async def test_recent_food_descriptions_returns_entries_within_window(db_session, settings, llm):
    from calobot.persistence.timeutil import today_in_timezone

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    today = today_in_timezone(settings.timezone)
    today_dt = dt.datetime.combine(today, dt.time(12, 0), tzinfo=dt.UTC)
    old_dt = dt.datetime.combine(today - dt.timedelta(days=10), dt.time(12, 0), tzinfo=dt.UTC)
    db_session.add(_make_entry(user.id, "pollo alla griglia", 150, 165, today_dt))
    db_session.add(_make_entry(user.id, "riso in bianco troppo vecchio", 100, 130, old_dt))
    await db_session.flush()

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["get_recent_food_descriptions"].handler(RecentDaysQuery(days=2))

    assert result["no_data"] is False
    descriptions = [e["description"] for e in result["entries"]]
    assert "pollo alla griglia" in descriptions
    assert "riso in bianco troppo vecchio" not in descriptions


async def test_recent_food_descriptions_reports_no_data_when_nothing_logged(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tools = await _registry(db_session, llm.gateway, settings.timezone, user)
    result = await tools["get_recent_food_descriptions"].handler(RecentDaysQuery(days=2))

    assert result["no_data"] is True


async def test_no_tool_schema_exposes_a_user_identifier(db_session, settings, llm):
    """specs/advice-agent - User identity is bound outside the conversation: the
    model must not be able to see, name or supply whose data is read."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    tools = await build_tool_registry(db_session, llm.gateway, user, settings.timezone)

    for tool in tools:
        schema_text = str(tool.args_schema.model_json_schema()).lower()
        assert "user_id" not in schema_text
        assert "telegram" not in schema_text
