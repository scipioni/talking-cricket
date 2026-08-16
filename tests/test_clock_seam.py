"""The clock seam (tasks 4.3, 4.4).

The guard test is the important one. `utcnow` is imported by name in a dozen
modules, so a seam that works today rots the moment someone adds a thirteenth that
reads the system clock directly - and a scenario that half-travels in time is the
worst possible failure for a test harness, because it produces confident wrong
answers about day boundaries rather than an error.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from harness.state import create_onboarded_user, food_extraction
from sqlalchemy import select

from calobot.persistence.models import FoodEntry
from calobot.persistence.seed import seed_all
from calobot.persistence.timeutil import day_in_timezone, today_in_timezone, utcnow

SRC = Path(__file__).resolve().parent.parent / "src" / "calobot"

# Two kinds of clock read, and only one of them belongs behind the seam:
#
#   domain time         what day is it, when did the user eat, has the draft expired
#                       -> must follow the simulated clock, or a scenario spanning
#                          days is meaningless
#
#   observability time  how long did this call take, when was this event emitted
#                       -> must NOT follow it: a simulated clock would report every
#                          latency as zero and stamp telemetry with the scenario's date
#
# The exemptions below are whole modules whose only clock reads are the second kind.
_ALLOWED = {
    SRC / "persistence" / "timeutil.py",  # the seam itself
    SRC / "telegram" / "logging_middleware.py",  # log timestamps
    SRC / "llm" / "gateway.py",  # call latency and telemetry timestamps
}

_EXCLUDED_DIRS = {
    SRC / "persistence" / "migrations",  # historical artefacts, not runtime reads
    SRC / "telemetry",  # observability throughout
}

_DIRECT_READS = re.compile(r"datetime\.now\(|\bdate\.today\(\)|\btime\.time\(\)")


def test_no_module_reads_the_system_clock_directly():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path in _ALLOWED or any(excluded in path.parents for excluded in _EXCLUDED_DIRS):
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if _DIRECT_READS.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {line.strip()}")

    assert not offenders, (
        "these read the system clock instead of calobot.persistence.timeutil, so a "
        "simulated clock would not reach them:\n  " + "\n  ".join(offenders)
    )


def test_the_clock_drives_utcnow(clock):
    clock.set(dt.datetime(2026, 5, 4, 12, 30, tzinfo=dt.UTC))

    assert utcnow() == dt.datetime(2026, 5, 4, 12, 30, tzinfo=dt.UTC)

    clock.advance(days=1, hours=2)
    assert utcnow() == dt.datetime(2026, 5, 5, 14, 30, tzinfo=dt.UTC)


def test_the_clock_is_uninstalled_after_a_test():
    """Guards the fixture itself: if simulated time leaked, every later test would be
    quietly running in 2026-03-02."""
    assert abs((utcnow() - dt.datetime.now(dt.UTC)).total_seconds()) < 5


def test_local_day_follows_the_configured_timezone(clock):
    rome = ZoneInfo("Europe/Rome")

    # 23:30 in Rome on 2 March is 22:30 UTC - still the 2nd locally.
    clock.set_local(dt.datetime(2026, 3, 2, 23, 30), rome)
    assert today_in_timezone(rome) == dt.date(2026, 3, 2)

    clock.advance(hours=1)  # 00:30 Rome on the 3rd
    assert today_in_timezone(rome) == dt.date(2026, 3, 3)


def test_advance_to_next_local_day_crosses_the_boundary(clock):
    rome = ZoneInfo("Europe/Rome")
    clock.set_local(dt.datetime(2026, 3, 2, 23, 30), rome)

    clock.advance_to_next_local_day(rome, at_hour=8)

    assert today_in_timezone(rome) == dt.date(2026, 3, 3)
    assert utcnow().astimezone(rome).hour == 8


async def test_a_stored_entry_is_stamped_with_the_simulated_instant(
    db_session, client, llm, clock
):
    """The reason models.py could not keep its own copy of utcnow(): an entry logged
    in simulated time must carry the simulated instant, or every day-attribution
    assertion built on it is meaningless."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    rome = ZoneInfo("Europe/Rome")
    clock.set_local(dt.datetime(2026, 3, 2, 13, 20), rome)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="noci", quantity_grams=10),
        {"selected_candidate_id": 1},
    )
    await client.say("ho mangiato 10g di noci")

    db_session.expire_all()
    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    # Read back through the production helper: SQLite hands back naive datetimes,
    # and day_in_timezone is what every read path uses to interpret them.
    assert day_in_timezone(entry.created_at, rome) == dt.date(2026, 3, 2)


async def test_entries_either_side_of_local_midnight_land_on_their_own_days(
    db_session, client, llm, clock
):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    rome = ZoneInfo("Europe/Rome")

    clock.set_local(dt.datetime(2026, 3, 2, 23, 45), rome)
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="noci", quantity_grams=10),
        {"selected_candidate_id": 1},
    )
    await client.say("spuntino di mezzanotte")

    clock.advance(minutes=30)  # 00:15 on the 3rd, in Rome
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="mela", quantity_grams=150),
        {"selected_candidate_id": None},
        {"kcal_per_100g": 52, "display_name_it": "mela"},
    )
    await client.say("e anche una mela")

    db_session.expire_all()
    entries = list((await db_session.execute(select(FoodEntry).order_by(FoodEntry.id))).scalars())
    days = [day_in_timezone(e.consumed_at, rome) for e in entries]

    assert days == [dt.date(2026, 3, 2), dt.date(2026, 3, 3)]


def test_the_clock_refuses_a_naive_instant(clock):
    with pytest.raises(ValueError, match="aware"):
        clock.set(dt.datetime(2026, 5, 4, 12, 30))
