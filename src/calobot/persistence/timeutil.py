"""Day-boundary helpers. Timestamps are stored in UTC; day boundaries are computed by
converting to a timezone passed as a parameter, never a hardcoded constant, so a later
per-user timezone only needs a different argument here (design.md - Timezone)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def day_in_timezone(moment: dt.datetime, tz: ZoneInfo) -> dt.date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(tz).date()


def today_in_timezone(tz: ZoneInfo) -> dt.date:
    return day_in_timezone(utcnow(), tz)


def start_of_day_utc(day: dt.date, tz: ZoneInfo) -> dt.datetime:
    local_midnight = dt.datetime.combine(day, dt.time.min, tzinfo=tz)
    return local_midnight.astimezone(dt.UTC)


def day_bounds_utc(day: dt.date, tz: ZoneInfo) -> tuple[dt.datetime, dt.datetime]:
    """Return [start, end) in UTC for the given local calendar day."""
    start = start_of_day_utc(day, tz)
    end = start_of_day_utc(day + dt.timedelta(days=1), tz)
    return start, end


def period_bounds_utc(
    period: str, reference_day: dt.date, tz: ZoneInfo
) -> tuple[dt.datetime, dt.datetime]:
    """period: 'day' | 'week' | 'month' | 'year'. Week starts Monday (ISO)."""
    if period == "day":
        return day_bounds_utc(reference_day, tz)
    if period == "week":
        start_day = reference_day - dt.timedelta(days=reference_day.weekday())
        end_day = start_day + dt.timedelta(days=7)
        return start_of_day_utc(start_day, tz), start_of_day_utc(end_day, tz)
    if period == "month":
        start_day = reference_day.replace(day=1)
        if start_day.month == 12:
            end_day = start_day.replace(year=start_day.year + 1, month=1)
        else:
            end_day = start_day.replace(month=start_day.month + 1)
        return start_of_day_utc(start_day, tz), start_of_day_utc(end_day, tz)
    if period == "year":
        start_day = reference_day.replace(month=1, day=1)
        end_day = start_day.replace(year=start_day.year + 1)
        return start_of_day_utc(start_day, tz), start_of_day_utc(end_day, tz)
    raise ValueError(f"unknown period: {period}")
