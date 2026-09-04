"""Report aggregation. See specs/reporting - Calorie/Weight/Activity report contents.
Deleted entries are already excluded by the repository functions this builds on
(specs/entry-correction - Soft deletion)."""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.repository import (
    get_entries_in_range,
    get_weight_entries_in_range,
)
from calobot.persistence.timeutil import period_bounds_utc, start_of_day_utc, today_local
from calobot.reporting.periods import Period

MIN_MEASUREMENTS_FOR_TREND = 3

# See design.md - Decisions: a single constant rather than a per-signal tuned
# threshold. Below this many elapsed/logged days in the *current* period, a signal
# reports itself as not having enough data rather than a weak or tentative pattern
# (specs/advice-agent - Absent data is reported as absent, not estimated).
MIN_DAYS_FOR_SIGNAL = 3

# Calorie-density trend labelling band: below this relative change the density is
# called stable rather than trending, since day-to-day noise in what gets logged
# would otherwise flip the label on negligible movement.
DENSITY_TREND_BAND = 0.05

# Day-period only: a day's logged activity kcal is credited back onto the budget
# before comparing against food eaten, capped and fractional to offset the known
# tendency of LLM-estimated activity kcal to run high (design.md - Decisions).
ACTIVITY_CREDIT_FRACTION = 0.5
ACTIVITY_CREDIT_CAP_KCAL = 600


def activity_credit_kcal(activity_kcal: float) -> float:
    return min(ACTIVITY_CREDIT_FRACTION * activity_kcal, ACTIVITY_CREDIT_CAP_KCAL)


@dataclass(frozen=True)
class FoodReport:
    total_kcal: float
    daily_average_kcal: float
    budget_kcal: float | None
    difference_kcal: float | None
    days_with_no_data: list[dt.date]
    has_data: bool
    activity_credit_kcal: float = 0.0


@dataclass(frozen=True)
class MacroReport:
    protein_total_g: float
    protein_avg_g: float
    fat_total_g: float
    fat_avg_g: float
    carbs_total_g: float
    carbs_avg_g: float
    fiber_total_g: float
    fiber_avg_g: float
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
    session: AsyncSession,
    user_id: int,
    period: Period,
    reference_day: dt.date,
    tz,
    budget_kcal: float | None,
    *,
    activity_kcal_today: float = 0.0,
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
    credit = 0.0
    if period == "day":
        start_7d = start_of_day_utc(reference_day - dt.timedelta(days=6), tz)
        end_7d = start_of_day_utc(reference_day + dt.timedelta(days=1), tz)
        avg_entries = await get_entries_in_range(session, "food", user_id, start_7d, end_7d)
        avg_days_with_data = {e.consumed_at.astimezone(tz).date() for e in avg_entries}
        num_days_counted = max(len(avg_days_with_data), 1)
        avg_total = sum(e.kcal for e in avg_entries)
        average = avg_total / num_days_counted
        credit = activity_credit_kcal(activity_kcal_today)
        difference = (total - (budget_kcal + credit)) if budget_kcal is not None else None
    else:
        average = total / num_days_counted
        difference = (average - budget_kcal) if budget_kcal is not None else None

    return FoodReport(
        total_kcal=total,
        daily_average_kcal=average,
        budget_kcal=budget_kcal,
        difference_kcal=difference,
        days_with_no_data=days_with_no_data,
        has_data=True,
        activity_credit_kcal=credit,
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


async def build_macro_report(
    session: AsyncSession, user_id: int, period: Period, reference_day: dt.date, tz
) -> MacroReport:
    """specs/reporting - Macro report contents. Each macro's total skips entries
    where that macro is absent independently of the others (an entry missing fiber
    still contributes to the protein total); the daily-average denominator is the
    days with any food logged, the same denominator the calorie report uses, so
    days with no logged food are identified rather than counted as zero-gram days."""
    start, end = period_bounds_utc(period, reference_day, tz)
    entries = await get_entries_in_range(session, "food", user_id, start, end)

    if not entries:
        return MacroReport(
            protein_total_g=0,
            protein_avg_g=0,
            fat_total_g=0,
            fat_avg_g=0,
            carbs_total_g=0,
            carbs_avg_g=0,
            fiber_total_g=0,
            fiber_avg_g=0,
            days_with_no_data=[],
            has_data=False,
        )

    days_with_data = {e.consumed_at.astimezone(tz).date() for e in entries}
    start_day = start.astimezone(tz).date()
    end_day = end.astimezone(tz).date()
    all_days = _all_days_in_range(start_day, end_day)
    days_with_no_data = [d for d in all_days if d not in days_with_data and d <= today_local()]
    num_days = max(len(days_with_data), 1)

    def total_and_avg(attr: str) -> tuple[float, float]:
        total = sum(v for e in entries if (v := getattr(e, attr)) is not None)
        return total, total / num_days

    protein_total, protein_avg = total_and_avg("protein_g")
    fat_total, fat_avg = total_and_avg("fat_g")
    carbs_total, carbs_avg = total_and_avg("carbs_g")
    fiber_total, fiber_avg = total_and_avg("fiber_g")

    return MacroReport(
        protein_total_g=protein_total,
        protein_avg_g=protein_avg,
        fat_total_g=fat_total,
        fat_avg_g=fat_avg,
        carbs_total_g=carbs_total,
        carbs_avg_g=carbs_avg,
        fiber_total_g=fiber_total,
        fiber_avg_g=fiber_avg,
        days_with_no_data=days_with_no_data,
        has_data=True,
    )


async def build_daily_macro_breakdown(
    session: AsyncSession, user_id: int, period: Period, reference_day: dt.date, tz
) -> dict[dt.date, dict[str, float]]:
    start, end = period_bounds_utc(period, reference_day, tz)
    entries = await get_entries_in_range(session, "food", user_id, start, end)
    breakdown: dict[dt.date, dict[str, float]] = {}
    for e in entries:
        day = e.consumed_at.astimezone(tz).date()
        day_totals = breakdown.setdefault(day, {"protein": 0.0, "fat": 0.0, "carbs": 0.0, "fiber": 0.0})
        day_totals["protein"] += e.protein_g or 0.0
        day_totals["fat"] += e.fat_g or 0.0
        day_totals["carbs"] += e.carbs_g or 0.0
        day_totals["fiber"] += e.fiber_g or 0.0
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


def _previous_period_start(period: Period, current_start_day: dt.date) -> dt.date:
    """The previous period's start date, derived from the *current* period's own
    start date (always day 1 of the month for "month", Jan 1 for "year", the Monday
    for "week") so subtracting a month/year is always a valid date by construction -
    see design.md - Decisions for why this isn't done via `reference_day` arithmetic
    fed back through `period_bounds_utc`."""
    if period == "day":
        return current_start_day - dt.timedelta(days=1)
    if period == "week":
        return current_start_day - dt.timedelta(days=7)
    if period == "month":
        if current_start_day.month == 1:
            return current_start_day.replace(year=current_start_day.year - 1, month=12)
        return current_start_day.replace(month=current_start_day.month - 1)
    if period == "year":
        return current_start_day.replace(year=current_start_day.year - 1)
    raise ValueError(f"unknown period: {period}")


@dataclass(frozen=True)
class PeriodComparison:
    period: Period
    calories_avg_current: float | None
    calories_avg_previous: float | None
    calories_avg_delta: float | None
    weight_change_current_kg: float | None
    weight_change_previous_kg: float | None
    weight_change_delta_kg: float | None
    activity_minutes_current: float
    activity_minutes_previous: float
    activity_minutes_delta: float
    has_current_data: bool
    has_previous_data: bool


@dataclass(frozen=True)
class LoggingConsistencySignal:
    ratio_current: float | None
    ratio_previous: float | None
    enough_data: bool


@dataclass(frozen=True)
class MealTimingSignal:
    typical_last_meal_hour_current: float | None
    typical_last_meal_hour_previous: float | None
    drift_hours: float | None
    enough_data: bool


CalorieDensityTrend = Literal["in aumento", "in calo", "stabile"]


@dataclass(frozen=True)
class CalorieDensitySignal:
    kcal_per_100g_current: float | None
    kcal_per_100g_previous: float | None
    trend: CalorieDensityTrend | None
    enough_data: bool


@dataclass(frozen=True)
class PeriodComparisonResult:
    comparison: PeriodComparison
    logging_consistency: LoggingConsistencySignal
    meal_timing: MealTimingSignal
    calorie_density: CalorieDensitySignal


def _days_elapsed_in_period(start_day: dt.date, end_day: dt.date) -> list[dt.date]:
    """Calendar days in [start_day, end_day) that have already happened, matching
    the `days_with_no_data` convention `build_food_report` already uses."""
    return [d for d in _all_days_in_range(start_day, end_day) if d <= today_local()]


def _logging_consistency_for_period(
    entries: list, start_day: dt.date, end_day: dt.date
) -> tuple[float | None, bool]:
    """`entries` must already carry local-time `consumed_at` values (see
    `_with_local_time`)."""
    elapsed = _days_elapsed_in_period(start_day, end_day)
    if len(elapsed) < MIN_DAYS_FOR_SIGNAL:
        return None, False
    days_with_data = {e.consumed_at.date() for e in entries}
    ratio = len({d for d in days_with_data if d in elapsed}) / len(elapsed)
    return ratio, True


def _typical_last_meal_hour(entries: list) -> float | None:
    """Median local hour (fractional) of each logged day's last meal. `entries` must
    already carry timezone-aware `consumed_at` values converted to local time by the
    caller, so this only groups and takes the last one per day."""
    by_day: dict[dt.date, dt.datetime] = {}
    for e in entries:
        day = e.consumed_at.date()
        if day not in by_day or e.consumed_at > by_day[day]:
            by_day[day] = e.consumed_at
    if len(by_day) < MIN_DAYS_FOR_SIGNAL:
        return None
    hours = [moment.hour + moment.minute / 60.0 for moment in by_day.values()]
    return statistics.median(hours)


def _calorie_density(entries: list) -> tuple[float | None, bool]:
    dense_entries = [e for e in entries if e.grams]
    days_with_data = {e.consumed_at.date() for e in dense_entries}
    if len(days_with_data) < MIN_DAYS_FOR_SIGNAL:
        return None, False
    total_kcal = sum(e.kcal for e in dense_entries)
    total_grams = sum(e.grams for e in dense_entries)
    if total_grams == 0:
        return None, False
    return total_kcal / total_grams * 100.0, True


def _density_trend(current: float, previous: float | None) -> CalorieDensityTrend | None:
    if previous is None or previous == 0:
        return None
    relative_change = (current - previous) / previous
    if relative_change > DENSITY_TREND_BAND:
        return "in aumento"
    if relative_change < -DENSITY_TREND_BAND:
        return "in calo"
    return "stabile"


async def build_period_comparison(
    session: AsyncSession,
    user_id: int,
    period: Period,
    reference_day: dt.date,
    tz,
    goal_kg: float | None,
) -> PeriodComparisonResult:
    """Deterministic period-over-period comparison and behavioural signals. See
    design.md - Decisions: the comparison figures are produced by calling the same
    `build_*_report` functions a report calls, once per period, so a comparison can
    never disagree with what a report for either period would show; the signals are
    computed from raw entries since no report dataclass keeps per-day/per-entry
    detail once it has produced a total."""
    current_start, current_end = period_bounds_utc(period, reference_day, tz)
    current_start_day = current_start.astimezone(tz).date()
    current_end_day = current_end.astimezone(tz).date()
    previous_start_day = _previous_period_start(period, current_start_day)
    # `previous_start_day` always lands within the previous period by construction
    # (design.md - Decisions), so any reference day inside it resolves the same
    # bounds `period_bounds_utc` would give the previous period directly.
    previous_reference_day = previous_start_day

    food_current, food_previous = (
        await build_food_report(session, user_id, period, reference_day, tz, None),
        await build_food_report(session, user_id, period, previous_reference_day, tz, None),
    )
    weight_current, weight_previous = (
        await build_weight_report(session, user_id, period, reference_day, tz, goal_kg),
        await build_weight_report(session, user_id, period, previous_reference_day, tz, goal_kg),
    )
    activity_current, activity_previous = (
        await build_activity_report(session, user_id, period, reference_day, tz),
        await build_activity_report(session, user_id, period, previous_reference_day, tz),
    )

    calories_current = food_current.daily_average_kcal if food_current.has_data else None
    calories_previous = food_previous.daily_average_kcal if food_previous.has_data else None
    calories_delta = (
        calories_current - calories_previous
        if calories_current is not None and calories_previous is not None
        else None
    )

    weight_current_change = weight_current.change_kg if weight_current.has_data else None
    weight_previous_change = weight_previous.change_kg if weight_previous.has_data else None
    weight_delta = (
        weight_current_change - weight_previous_change
        if weight_current_change is not None and weight_previous_change is not None
        else None
    )

    activity_current_minutes = activity_current.total_minutes if activity_current.has_data else 0.0
    activity_previous_minutes = activity_previous.total_minutes if activity_previous.has_data else 0.0

    comparison = PeriodComparison(
        period=period,
        calories_avg_current=calories_current,
        calories_avg_previous=calories_previous,
        calories_avg_delta=calories_delta,
        weight_change_current_kg=weight_current_change,
        weight_change_previous_kg=weight_previous_change,
        weight_change_delta_kg=weight_delta,
        activity_minutes_current=activity_current_minutes,
        activity_minutes_previous=activity_previous_minutes,
        activity_minutes_delta=activity_current_minutes - activity_previous_minutes,
        has_current_data=food_current.has_data or activity_current.has_data or weight_current.has_data,
        has_previous_data=food_previous.has_data or activity_previous.has_data or weight_previous.has_data,
    )

    food_entries_current = await get_entries_in_range(session, "food", user_id, current_start, current_end)
    previous_start, previous_end = start_of_day_utc(previous_start_day, tz), current_start
    food_entries_previous = await get_entries_in_range(session, "food", user_id, previous_start, previous_end)

    local_current = [_with_local_time(e, tz) for e in food_entries_current]
    local_previous = [_with_local_time(e, tz) for e in food_entries_previous]

    consistency_current, consistency_enough = _logging_consistency_for_period(
        local_current, current_start_day, current_end_day
    )
    consistency_previous, _ = _logging_consistency_for_period(
        local_previous, previous_start_day, current_start_day
    )
    logging_consistency = LoggingConsistencySignal(
        ratio_current=consistency_current,
        ratio_previous=consistency_previous,
        enough_data=consistency_enough,
    )

    timing_current = _typical_last_meal_hour(local_current)
    timing_previous = _typical_last_meal_hour(local_previous)
    drift_hours = (
        timing_current - timing_previous
        if timing_current is not None and timing_previous is not None
        else None
    )
    meal_timing = MealTimingSignal(
        typical_last_meal_hour_current=timing_current,
        typical_last_meal_hour_previous=timing_previous,
        drift_hours=drift_hours,
        enough_data=timing_current is not None,
    )

    density_current, density_enough = _calorie_density(local_current)
    density_previous, _ = _calorie_density(local_previous)
    calorie_density = CalorieDensitySignal(
        kcal_per_100g_current=density_current,
        kcal_per_100g_previous=density_previous,
        trend=_density_trend(density_current, density_previous) if density_current is not None else None,
        enough_data=density_enough,
    )

    return PeriodComparisonResult(
        comparison=comparison,
        logging_consistency=logging_consistency,
        meal_timing=meal_timing,
        calorie_density=calorie_density,
    )


async def meal_timing_signal_for_range(
    session: AsyncSession, user_id: int, start: dt.datetime, end: dt.datetime, tz
) -> float | None:
    """Public wrapper around `_typical_last_meal_hour` for a caller-chosen range
    rather than a whole period - used by `calobot.advice.memory` to compare the
    weeks before and after a piece of advice (design.md there)."""
    entries = await get_entries_in_range(session, "food", user_id, start, end)
    return _typical_last_meal_hour([_with_local_time(e, tz) for e in entries])


async def logging_consistency_signal_for_range(
    session: AsyncSession, user_id: int, start: dt.datetime, end: dt.datetime, tz
) -> float | None:
    """Public wrapper around `_logging_consistency_for_period` for a caller-chosen
    range, mirroring `meal_timing_signal_for_range`."""
    entries = await get_entries_in_range(session, "food", user_id, start, end)
    local_entries = [_with_local_time(e, tz) for e in entries]
    start_day = start.astimezone(tz).date()
    end_day = end.astimezone(tz).date()
    ratio, enough = _logging_consistency_for_period(local_entries, start_day, end_day)
    return ratio if enough else None


def _with_local_time(entry, tz):
    """Returns a shallow stand-in exposing `consumed_at` converted to local time,
    grams and kcal, so the signal helpers above can group by local calendar day
    without repeating the timezone conversion at each call site."""
    return _LocalFoodEntry(
        consumed_at=entry.consumed_at.astimezone(tz),
        grams=entry.grams,
        kcal=entry.kcal,
    )


@dataclass(frozen=True)
class _LocalFoodEntry:
    consumed_at: dt.datetime
    grams: float | None
    kcal: float
