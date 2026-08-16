"""Report aggregation. See specs/reporting - Calorie/Weight/Activity report contents.
Deleted entries are already excluded by the repository functions this builds on
(specs/entry-correction - Soft deletion)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.repository import (
    get_entries_in_range,
    get_weight_entries_in_range,
)
from calobot.persistence.timeutil import period_bounds_utc, today_local
from calobot.reporting.periods import Period

MIN_MEASUREMENTS_FOR_TREND = 3


@dataclass(frozen=True)
class FoodReport:
    total_kcal: float
    daily_average_kcal: float
    budget_kcal: float | None
    difference_kcal: float | None
    days_with_no_data: list[dt.date]
    has_data: bool


@dataclass(frozen=True)
class ActivityReport:
    total_minutes: float
    days_with_activity: int
    total_kcal: float
    has_data: bool


@dataclass(frozen=True)
class WeightPoint:
    day: dt.date
    kg: float


@dataclass(frozen=True)
class WeightReport:
    start_kg: float | None
    end_kg: float | None
    change_kg: float | None
    remaining_to_goal_kg: float | None
    projected_date: dt.date | None
    projection_unavailable_reason: str | None  # None if a projection was produced
    points: list[WeightPoint]
    has_data: bool


def _all_days_in_range(start_day: dt.date, end_day: dt.date) -> list[dt.date]:
    days = []
    d = start_day
    while d < end_day:
        days.append(d)
        d += dt.timedelta(days=1)
    return days


async def build_food_report(
    session: AsyncSession, user_id: int, period: Period, reference_day: dt.date, tz, budget_kcal: float | None
) -> FoodReport:
    start, end = period_bounds_utc(period, reference_day, tz)
    entries = await get_entries_in_range(session, "food", user_id, start, end)

    if not entries:
        return FoodReport(
            total_kcal=0,
            daily_average_kcal=0,
            budget_kcal=budget_kcal,
            difference_kcal=None,
            days_with_no_data=[],
            has_data=False,
        )

    total = sum(e.kcal for e in entries)
    days_with_data = {e.consumed_at.astimezone(tz).date() for e in entries}
    start_day = start.astimezone(tz).date()
    end_day = end.astimezone(tz).date()
    all_days = _all_days_in_range(start_day, end_day)
    days_with_no_data = [d for d in all_days if d not in days_with_data and d <= today_local()]

    num_days_counted = max(len(days_with_data), 1)
    average = total / num_days_counted
    difference = (average - budget_kcal) if budget_kcal is not None else None

    return FoodReport(
        total_kcal=total,
        daily_average_kcal=average,
        budget_kcal=budget_kcal,
        difference_kcal=difference,
        days_with_no_data=days_with_no_data,
        has_data=True,
    )


async def build_daily_kcal_breakdown(
    session: AsyncSession, user_id: int, period: Period, reference_day: dt.date, tz
) -> dict[dt.date, float]:
    start, end = period_bounds_utc(period, reference_day, tz)
    entries = await get_entries_in_range(session, "food", user_id, start, end)
    breakdown: dict[dt.date, float] = {}
    for e in entries:
        day = e.consumed_at.astimezone(tz).date()
        breakdown[day] = breakdown.get(day, 0.0) + e.kcal
    return breakdown


async def build_activity_report(
    session: AsyncSession, user_id: int, period: Period, reference_day: dt.date, tz
) -> ActivityReport:
    start, end = period_bounds_utc(period, reference_day, tz)
    entries = await get_entries_in_range(session, "activity", user_id, start, end)

    if not entries:
        return ActivityReport(total_minutes=0, days_with_activity=0, total_kcal=0, has_data=False)

    total_minutes = sum(e.duration_minutes for e in entries)
    total_kcal = sum(e.kcal for e in entries)
    days = {e.performed_at.astimezone(tz).date() for e in entries}

    return ActivityReport(
        total_minutes=total_minutes,
        days_with_activity=len(days),
        total_kcal=total_kcal,
        has_data=True,
    )


def _linear_trend(points: list[WeightPoint]) -> tuple[float, float] | None:
    """Least-squares slope (kg/day) and intercept over (day_ordinal, kg). None if
    fewer than MIN_MEASUREMENTS_FOR_TREND points."""
    if len(points) < MIN_MEASUREMENTS_FOR_TREND:
        return None
    xs = [p.day.toordinal() for p in points]
    ys = [p.kg for p in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    slope = numerator / denominator
    intercept = mean_y - slope * mean_x
    return slope, intercept


async def build_weight_report(
    session: AsyncSession, user_id: int, period: Period, reference_day: dt.date, tz, goal_kg: float | None
) -> WeightReport:
    start, end = period_bounds_utc(period, reference_day, tz)
    start_day = start.astimezone(tz).date()
    end_day = (end.astimezone(tz).date()) - dt.timedelta(days=1)
    entries = await get_weight_entries_in_range(session, user_id, start_day, end_day + dt.timedelta(days=1))

    if not entries:
        return WeightReport(
            start_kg=None,
            end_kg=None,
            change_kg=None,
            remaining_to_goal_kg=None,
            projected_date=None,
            projection_unavailable_reason="nessun dato nel periodo",
            points=[],
            has_data=False,
        )

    points = [WeightPoint(day=e.day, kg=e.kg) for e in entries]
    start_kg = points[0].kg
    end_kg = points[-1].kg
    change = end_kg - start_kg
    remaining = (goal_kg - end_kg) if goal_kg is not None else None

    projected_date: dt.date | None = None
    reason: str | None = None

    trend = _linear_trend(points)
    if trend is None:
        reason = "servono più misurazioni per calcolare una tendenza"
    elif goal_kg is None:
        reason = "nessun obiettivo impostato"
    else:
        slope, intercept = trend
        moving_towards_goal = (slope < 0 and end_kg > goal_kg) or (slope > 0 and end_kg < goal_kg)
        if not moving_towards_goal:
            reason = "la tendenza recente non si sta muovendo verso l'obiettivo"
        else:
            target_ordinal = (goal_kg - intercept) / slope
            projected_date = dt.date.fromordinal(round(target_ordinal))

    return WeightReport(
        start_kg=start_kg,
        end_kg=end_kg,
        change_kg=change,
        remaining_to_goal_kg=remaining,
        projected_date=projected_date,
        projection_unavailable_reason=reason,
        points=points,
        has_data=True,
    )
