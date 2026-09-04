"""Tests for `build_period_comparison` (tasks.md 1.5,
openspec/changes/advice-longitudinal-signals). Uses the `clock` fixture so "today"
is fixed and every entry's day-attribution is deterministic."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from calobot.persistence.models import ActivityEntry, FoodEntry, Provenance, WeightEntry
from calobot.persistence.repository import create_user
from calobot.reporting.aggregation import MIN_DAYS_FOR_SIGNAL, _previous_period_start, build_period_comparison

TZ = ZoneInfo("Europe/Rome")


def _food(user_id: int, grams: float, kcal: float, when: dt.datetime) -> FoodEntry:
    return FoodEntry(
        user_id=user_id,
        description="pasto",
        grams=grams,
        kcal_per_100g=kcal / grams * 100,
        kcal=kcal,
        provenance=Provenance.tabella,
        consumed_at=when,
    )


def test_previous_period_start_is_always_valid():
    assert _previous_period_start("day", dt.date(2026, 1, 1)) == dt.date(2025, 12, 31)
    assert _previous_period_start("week", dt.date(2026, 3, 2)) == dt.date(2026, 2, 23)
    assert _previous_period_start("month", dt.date(2026, 1, 1)) == dt.date(2025, 12, 1)
    assert _previous_period_start("month", dt.date(2026, 3, 1)) == dt.date(2026, 2, 1)
    # A leap-year edge: Mar 1 of a leap year steps back to Feb 1, never Feb 29/30/31.
    assert _previous_period_start("year", dt.date(2024, 1, 1)) == dt.date(2023, 1, 1)


async def test_comparison_reports_deltas_matching_the_report_path(db_session, clock):
    user = await create_user(db_session, telegram_user_id=101)
    today = clock.now().astimezone(TZ).date()  # a Monday, week fixture's clock is set to
    this_week_monday = today - dt.timedelta(days=today.weekday())
    last_week_monday = this_week_monday - dt.timedelta(days=7)

    for offset in range(3):
        current_day = this_week_monday + dt.timedelta(days=offset)
        previous_day = last_week_monday + dt.timedelta(days=offset)
        db_session.add(_food(user.id, 200, 400, dt.datetime.combine(current_day, dt.time(12), tzinfo=TZ)))
        db_session.add(_food(user.id, 200, 200, dt.datetime.combine(previous_day, dt.time(12), tzinfo=TZ)))
    db_session.add(
        ActivityEntry(
            user_id=user.id,
            activity="camminata",
            duration_minutes=30,
            met=4.0,
            kcal=150,
            provenance=Provenance.tabella,
            performed_at=dt.datetime.combine(this_week_monday, dt.time(9), tzinfo=TZ),
        )
    )
    await db_session.flush()

    result = await build_period_comparison(db_session, user.id, "week", today, TZ, goal_kg=None)

    assert result.comparison.has_current_data is True
    assert result.comparison.has_previous_data is True
    assert result.comparison.calories_avg_current == 400
    assert result.comparison.calories_avg_previous == 200
    assert result.comparison.calories_avg_delta == 200
    assert result.comparison.activity_minutes_current == 30
    assert result.comparison.activity_minutes_previous == 0


async def test_comparison_with_no_previous_period_data(db_session, clock):
    user = await create_user(db_session, telegram_user_id=102)
    today = clock.now().astimezone(TZ).date()
    db_session.add(_food(user.id, 200, 400, dt.datetime.combine(today, dt.time(12), tzinfo=TZ)))
    await db_session.flush()

    result = await build_period_comparison(db_session, user.id, "week", today, TZ, goal_kg=None)

    assert result.comparison.has_current_data is True
    assert result.comparison.has_previous_data is False
    assert result.comparison.calories_avg_previous is None
    assert result.comparison.calories_avg_delta is None


async def test_comparison_with_no_data_at_all(db_session, clock):
    user = await create_user(db_session, telegram_user_id=103)
    today = clock.now().astimezone(TZ).date()

    result = await build_period_comparison(db_session, user.id, "week", today, TZ, goal_kg=None)

    assert result.comparison.has_current_data is False
    assert result.logging_consistency.enough_data is False
    assert result.meal_timing.enough_data is False
    assert result.calorie_density.enough_data is False


async def test_signals_report_insufficient_data_below_the_minimum(db_session, clock):
    user = await create_user(db_session, telegram_user_id=104)
    today = clock.now().astimezone(TZ).date()
    this_week_monday = today - dt.timedelta(days=today.weekday())
    assert MIN_DAYS_FOR_SIGNAL > 1
    db_session.add(_food(user.id, 200, 400, dt.datetime.combine(this_week_monday, dt.time(12), tzinfo=TZ)))
    await db_session.flush()

    result = await build_period_comparison(db_session, user.id, "week", today, TZ, goal_kg=None)

    assert result.logging_consistency.enough_data is False
    assert result.meal_timing.enough_data is False
    assert result.calorie_density.enough_data is False


async def test_weight_change_delta_between_periods(db_session, clock):
    user = await create_user(db_session, telegram_user_id=105)
    today = clock.now().astimezone(TZ).date()
    this_week_monday = today - dt.timedelta(days=today.weekday())
    last_week_monday = this_week_monday - dt.timedelta(days=7)

    db_session.add(WeightEntry(user_id=user.id, day=this_week_monday, kg=80.0))
    db_session.add(WeightEntry(user_id=user.id, day=this_week_monday + dt.timedelta(days=2), kg=79.5))
    db_session.add(WeightEntry(user_id=user.id, day=last_week_monday, kg=81.0))
    db_session.add(WeightEntry(user_id=user.id, day=last_week_monday + dt.timedelta(days=2), kg=81.0))
    await db_session.flush()

    result = await build_period_comparison(db_session, user.id, "week", today, TZ, goal_kg=None)

    assert result.comparison.weight_change_current_kg == -0.5
    assert result.comparison.weight_change_previous_kg == 0.0
    assert result.comparison.weight_change_delta_kg == -0.5
