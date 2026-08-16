from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from calobot.persistence.models import ActivityEntry, FoodEntry, Provenance, WeightEntry
from calobot.persistence.repository import create_user
from calobot.reporting.aggregation import (
    build_activity_report,
    build_food_report,
    build_weight_report,
)
from calobot.reporting.charts import render_calorie_chart, render_weight_chart
from calobot.reporting.periods import parse_period

TZ = ZoneInfo("Europe/Rome")


def test_parse_period_conversational():
    assert parse_period("questo mese") == "month"
    assert parse_period("l'ultima settimana") == "week"
    assert parse_period("quest'anno") == "year"
    assert parse_period(None) == "day"
    assert parse_period("oggi") == "day"


async def test_food_report_names_days_with_no_data(db_session):
    user = await create_user(db_session, telegram_user_id=1)
    today = dt.datetime.now(TZ)
    db_session.add(
        FoodEntry(
            user_id=user.id,
            description="mela",
            grams=180,
            kcal_per_100g=52,
            kcal=93.6,
            provenance=Provenance.tabella,
            consumed_at=today,
        )
    )
    await db_session.flush()

    report = await build_food_report(db_session, user.id, "week", today.date(), TZ, budget_kcal=2000)
    assert report.has_data
    assert report.total_kcal == 93.6
    assert today.date() not in report.days_with_no_data


async def test_food_report_empty_period(db_session):
    user = await create_user(db_session, telegram_user_id=2)
    report = await build_food_report(db_session, user.id, "week", dt.date.today(), TZ, budget_kcal=2000)
    assert report.has_data is False


async def test_activity_report_totals(db_session):
    user = await create_user(db_session, telegram_user_id=3)
    now = dt.datetime.now(dt.UTC)
    db_session.add(
        ActivityEntry(
            user_id=user.id,
            activity="camminata",
            duration_minutes=30,
            met=3.5,
            kcal=150,
            provenance=Provenance.tabella,
            performed_at=now,
        )
    )
    await db_session.flush()

    report = await build_activity_report(db_session, user.id, "week", dt.date.today(), TZ)
    assert report.has_data
    assert report.total_minutes == 30
    assert report.total_kcal == 150


async def test_weight_report_trend_and_projection(db_session):
    user = await create_user(db_session, telegram_user_id=4)
    base = dt.date.today() - dt.timedelta(days=6)
    for i, kg in enumerate([90, 89.5, 89, 88.5, 88, 87.5, 87]):
        db_session.add(WeightEntry(user_id=user.id, kg=kg, day=base + dt.timedelta(days=i)))
    await db_session.flush()

    report = await build_weight_report(
        db_session, user.id, "week", dt.date.today(), TZ, goal_kg=80.0
    )
    assert report.has_data
    assert report.start_kg == 90
    assert report.end_kg == 87
    assert report.change_kg == -3
    assert report.projected_date is not None


async def test_weight_report_too_few_measurements(db_session):
    user = await create_user(db_session, telegram_user_id=5)
    db_session.add(WeightEntry(user_id=user.id, kg=80, day=dt.date.today()))
    await db_session.flush()

    report = await build_weight_report(
        db_session, user.id, "week", dt.date.today(), TZ, goal_kg=75.0
    )
    assert report.has_data
    assert report.projected_date is None
    assert "misurazioni" in report.projection_unavailable_reason


def test_render_charts_produce_png_bytes():
    from calobot.reporting.aggregation import WeightPoint

    points = [
        WeightPoint(day=dt.date.today() - dt.timedelta(days=i), kg=80 - i * 0.1)
        for i in range(10, 0, -1)
    ]
    png = render_weight_chart(points, goal_kg=75.0, projected_date=dt.date.today() + dt.timedelta(days=30))
    assert png.startswith(b"\x89PNG")

    daily = {dt.date.today() - dt.timedelta(days=i): 1800 + i * 10 for i in range(7)}
    png2 = render_calorie_chart(daily, budget_kcal=2000)
    assert png2.startswith(b"\x89PNG")


def test_render_weight_chart_handles_italian_accents():
    from calobot.reporting.aggregation import WeightPoint

    points = [WeightPoint(day=dt.date.today(), kg=80.0)]
    png = render_weight_chart(points, goal_kg=None, projected_date=None)
    assert png.startswith(b"\x89PNG")
