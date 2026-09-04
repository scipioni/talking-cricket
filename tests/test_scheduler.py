"""Tests for the in-process job scheduler (openspec/changes/background-scheduler).
Uses short real intervals with real `asyncio.sleep` rather than a fake clock: the
scheduler's own granularity is a tick, not a moment, so sub-second real delays are
enough to exercise it deterministically without flakiness."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from calobot.scheduler import Scheduler

TICK = 0.02


async def _run_briefly(scheduler: Scheduler, seconds: float) -> None:
    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(seconds)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_a_registered_job_runs_at_its_interval():
    calls = []

    async def job() -> None:
        calls.append(1)

    scheduler = Scheduler(tick_interval_seconds=TICK)
    scheduler.register("count", TICK, job)

    await _run_briefly(scheduler, TICK * 6)

    assert len(calls) >= 3


async def test_duplicate_registration_is_rejected():
    scheduler = Scheduler(tick_interval_seconds=TICK)

    async def job() -> None:
        pass

    scheduler.register("dup", TICK, job)
    with pytest.raises(ValueError):
        scheduler.register("dup", TICK, job)


async def test_overlapping_run_is_skipped_and_later_ticks_still_fire():
    started = []
    release = asyncio.Event()

    async def slow_job() -> None:
        started.append(1)
        await release.wait()

    scheduler = Scheduler(tick_interval_seconds=TICK)
    scheduler.register("slow", TICK, slow_job)

    task = asyncio.create_task(scheduler.run())
    # Let several ticks elapse while the first run is still blocked on the event.
    await asyncio.sleep(TICK * 5)
    assert len(started) == 1  # overlapping runs were skipped, not started again

    release.set()
    await asyncio.sleep(TICK * 3)
    assert len(started) >= 2  # a fresh run started once the previous one finished

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_raising_job_does_not_stop_the_scheduler_or_other_jobs():
    other_calls = []

    async def failing_job() -> None:
        raise RuntimeError("boom")

    async def other_job() -> None:
        other_calls.append(1)

    scheduler = Scheduler(tick_interval_seconds=TICK)
    scheduler.register("failing", TICK, failing_job)
    scheduler.register("other", TICK, other_job)

    await _run_briefly(scheduler, TICK * 6)

    assert len(other_calls) >= 3


async def test_shutdown_waits_for_a_fast_in_flight_run():
    finished = []

    async def fast_job() -> None:
        await asyncio.sleep(TICK)
        finished.append(1)

    scheduler = Scheduler(tick_interval_seconds=TICK, shutdown_grace_seconds=TICK * 10)
    scheduler.register("fast", TICK, fast_job)

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(TICK * 1.5)  # let the job start, but not finish
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert finished == [1]


async def test_shutdown_does_not_hang_past_the_grace_period():
    async def never_finishes() -> None:
        await asyncio.sleep(1000)

    scheduler = Scheduler(tick_interval_seconds=TICK, shutdown_grace_seconds=TICK)
    scheduler.register("stuck", TICK, never_finishes)

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(TICK * 1.5)

    task.cancel()
    await asyncio.wait_for(
        asyncio.gather(task, return_exceptions=True), timeout=TICK * 20
    )


async def test_disabled_scheduler_runs_no_job():
    calls = []

    async def job() -> None:
        calls.append(1)

    scheduler = Scheduler(enabled=False, tick_interval_seconds=TICK)
    scheduler.register("never", TICK, job)

    await _run_briefly(scheduler, TICK * 5)

    assert calls == []


async def test_no_jobs_registered_runs_and_stops_cleanly():
    scheduler = Scheduler(tick_interval_seconds=TICK)
    await _run_briefly(scheduler, TICK * 3)
