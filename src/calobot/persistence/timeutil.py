"""Day-boundary helpers, and the single seam through which the system reads the
current instant.

Timestamps are stored in UTC; day boundaries are computed by converting to a
timezone passed as a parameter, never a hardcoded constant, so a later per-user
timezone only needs a different argument here (design.md - Timezone).

Every read of "now" in this codebase goes through `utcnow()` (or `today_local()`,
which is derived from it), and `utcnow()` reads a provider that can be replaced.
This is what lets a simulated conversation span days without touching the system
clock (openspec/changes/calobot-simulation-harness/specs/conversation-simulation -
Simulated time). Patching per-module was rejected: `utcnow` is imported by name in
several places, so the patch set is a list that silently rots as modules are added,
and a missed one produces code that half-travels in time.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from zoneinfo import ZoneInfo

# Matches an explicit clock time such as "alle 15", "alle le 15:30", "ore 9.05".
_EXPLICIT_TIME_RE = re.compile(r"(?:alle\s+(?:le\s+)?|ore\s+)(\d{1,2})(?:[:.,](\d{2}))?")


def _system_clock() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


_now_provider: Callable[[], dt.datetime] = _system_clock


def set_clock(provider: Callable[[], dt.datetime]) -> None:
    """Replace the source of the current instant. Intended for simulated runs and
    tests; production never calls it."""
    global _now_provider
    _now_provider = provider


def reset_clock() -> None:
    global _now_provider
    _now_provider = _system_clock


def utcnow() -> dt.datetime:
    # Deliberately an indirection rather than a rebindable name: SQLAlchemy column
    # defaults capture this function object at class-definition time, so the
    # provider has to be read per call for those to follow the clock too.
    return _now_provider()


def today_local() -> dt.date:
    """The system-local calendar date, as `date.today()` returns it.

    Kept local rather than converted to a configured timezone, because that would be
    a behaviour change; routed through the clock so that simulated time reaches the
    call sites that use it.
    """
    return utcnow().astimezone().date()


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


def _parse_explicit_time(when_text: str) -> dt.time | None:
    match = _EXPLICIT_TIME_RE.search(when_text.lower())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return dt.time(hour, minute)


def resolve_when_text(when_text: str | None, tz: ZoneInfo, now: dt.datetime) -> dt.datetime:
    """Resolves a free-text temporal phrase (as extracted into `when_text`) against
    `now`, honouring an explicit day ('ieri') and/or clock time ('alle 15') stated in
    it. Day and time-of-day are resolved independently and both default to `now`'s
    local day/time in `tz`, so "alle 15" alone shifts only the hour and "ieri" alone
    shifts only the day.
    """
    if not when_text:
        return now
    local_now = now.astimezone(tz)
    day_offset = -1 if "ieri" in when_text.lower() else 0
    explicit_time = _parse_explicit_time(when_text)
    if day_offset == 0 and explicit_time is None:
        return now
    target_date = local_now.date() + dt.timedelta(days=day_offset)
    target_time = explicit_time or local_now.time()
    local_dt = dt.datetime.combine(target_date, target_time, tzinfo=tz)
    return local_dt.astimezone(dt.UTC)


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
