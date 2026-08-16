"""Chart rendering. See specs/reporting - Charts: weight charts show points, a 7-day
moving average (only where computable), a goal line and a projection; calorie charts
show daily totals against the budget line. Agg backend + non-interactive only
(design.md - matplotlib rendering to PNG, sent as a photo)."""

from __future__ import annotations

import datetime as dt
import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from calobot.reporting.aggregation import WeightPoint  # noqa: E402

MOVING_AVERAGE_WINDOW_DAYS = 7
MIN_POINTS_FOR_MOVING_AVERAGE = 3


def _moving_average(points: list[WeightPoint]) -> list[tuple[dt.date, float] | None]:
    """One value per point, or None where the trailing window has too few real
    measurements to average (specs/reporting - 'gaps are not interpolated as if
    measured')."""
    result: list[tuple[dt.date, float] | None] = []
    for i, point in enumerate(points):
        window_start = point.day - dt.timedelta(days=MOVING_AVERAGE_WINDOW_DAYS - 1)
        window = [p for p in points[: i + 1] if p.day >= window_start]
        if len(window) < MIN_POINTS_FOR_MOVING_AVERAGE:
            result.append(None)
        else:
            avg = sum(p.kg for p in window) / len(window)
            result.append((point.day, avg))
    return result


def render_weight_chart(
    points: list[WeightPoint],
    goal_kg: float | None,
    projected_date: dt.date | None,
) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)

    days = [p.day for p in points]
    kgs = [p.kg for p in points]
    ax.plot(days, kgs, "o", color="#3B6EA5", label="misurazioni", markersize=5)

    averages = _moving_average(points)
    avg_days = [a[0] for a in averages if a is not None]
    avg_values = [a[1] for a in averages if a is not None]
    if avg_days:
        ax.plot(avg_days, avg_values, "-", color="#D9822B", linewidth=2, label="media 7 giorni")

    if goal_kg is not None:
        ax.axhline(goal_kg, color="#4C9A5A", linestyle="--", linewidth=1.5, label="obiettivo")

    if projected_date is not None and goal_kg is not None:
        ax.plot(
            [days[-1], projected_date],
            [kgs[-1], goal_kg],
            ":",
            color="#4C9A5A",
            linewidth=1,
        )

    ax.set_ylabel("peso (kg)")
    ax.set_title("Andamento del peso")
    ax.legend(loc="best")
    fig.autofmt_xdate()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def render_calorie_chart(daily_kcal: dict[dt.date, float], budget_kcal: float | None) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)

    days = sorted(daily_kcal.keys())
    values = [daily_kcal[d] for d in days]
    ax.bar(days, values, color="#3B6EA5", label="calorie giornaliere")

    if budget_kcal is not None:
        ax.axhline(budget_kcal, color="#D9822B", linestyle="--", linewidth=1.5, label="budget")

    ax.set_ylabel("kcal")
    ax.set_title("Calorie giornaliere")
    ax.legend(loc="best")
    fig.autofmt_xdate()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
