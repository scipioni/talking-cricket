from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from calobot.persistence.timeutil import resolve_when_text

TZ = ZoneInfo("Europe/Rome")
NOW = dt.datetime(2026, 8, 17, 9, 0, tzinfo=dt.UTC)  # 11:00 Europe/Rome (summer, UTC+2)


def test_no_when_text_returns_now():
    assert resolve_when_text(None, TZ, NOW) == NOW


def test_ieri_shifts_only_the_day():
    resolved = resolve_when_text("ieri sera", TZ, NOW)
    local = resolved.astimezone(TZ)
    assert local.date() == dt.date(2026, 8, 16)
    assert (local.hour, local.minute) == (11, 0)  # time-of-day unchanged


def test_explicit_time_shifts_only_the_hour():
    resolved = resolve_when_text("alle 15", TZ, NOW)
    local = resolved.astimezone(TZ)
    assert local.date() == dt.date(2026, 8, 17)  # today, unchanged
    assert (local.hour, local.minute) == (15, 0)


def test_ieri_and_explicit_time_combine():
    resolved = resolve_when_text("alle 15 di ieri", TZ, NOW)
    local = resolved.astimezone(TZ)
    assert local.date() == dt.date(2026, 8, 16)
    assert (local.hour, local.minute) == (15, 0)


def test_explicit_time_with_minutes():
    resolved = resolve_when_text("alle 15:30", TZ, NOW)
    local = resolved.astimezone(TZ)
    assert (local.hour, local.minute) == (15, 30)


def test_out_of_range_time_is_ignored():
    resolved = resolve_when_text("alle 99", TZ, NOW)
    assert resolved == NOW
