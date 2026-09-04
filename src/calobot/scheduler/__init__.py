"""In-process periodic job scheduler. See specs/background-scheduling in full, and
design.md there for why `Scheduler.run()` is meant to sit directly inside
`asyncio.gather` rather than as a detached task like `telemetry_history`'s listener:
that is what lets the same cancellation that stops polling deliver a `CancelledError`
into this loop, where it is turned into a bounded-grace-period shutdown.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

JobFunc = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class Job:
    name: str
    interval_seconds: float
    func: JobFunc


class Scheduler:
    def __init__(
        self,
        *,
        enabled: bool = True,
        tick_interval_seconds: float = 60.0,
        shutdown_grace_seconds: float = 10.0,
    ) -> None:
        self._enabled = enabled
        self._tick_interval_seconds = tick_interval_seconds
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._jobs: dict[str, Job] = {}
        self._last_run_at: dict[str, float] = {}
        self._running: dict[str, asyncio.Task[None]] = {}

    def register(self, name: str, interval_seconds: float, func: JobFunc) -> None:
        """Registers a named job. See specs/background-scheduling - Jobs are
        registered explicitly at startup: must happen before `run()` starts."""
        if name in self._jobs:
            raise ValueError(f"job already registered: {name}")
        self._jobs[name] = Job(name=name, interval_seconds=interval_seconds, func=func)

    async def run(self) -> None:
        """Runs forever until cancelled. A no-op (returns immediately) when the
        scheduler is disabled, per specs/background-scheduling - The scheduler can
        be disabled entirely."""
        if not self._enabled:
            logger.info("scheduler disabled at startup; no job will run")
            return

        loop = asyncio.get_event_loop()
        now = loop.time()
        for name in self._jobs:
            self._last_run_at[name] = now

        try:
            while True:
                await asyncio.sleep(self._tick_interval_seconds)
                self._tick(loop.time())
        except asyncio.CancelledError:
            await self._shutdown()
            raise

    def _tick(self, now: float) -> None:
        for name, job in self._jobs.items():
            running_task = self._running.get(name)
            if running_task is not None and not running_task.done():
                logger.warning("scheduler: skipping '%s', previous run still in progress", name)
                continue
            if now - self._last_run_at.get(name, now) < job.interval_seconds:
                continue
            self._last_run_at[name] = now
            self._running[name] = asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: Job) -> None:
        try:
            await job.func()
        except Exception:
            logger.exception("scheduler: job '%s' raised", job.name)

    async def _shutdown(self) -> None:
        """See specs/background-scheduling - Shutdown is bounded and clean. No new
        run is launched once this runs, since it's only reached by `run()`'s own
        loop exiting on cancellation."""
        in_flight = [t for t in self._running.values() if not t.done()]
        if not in_flight:
            return
        _done, pending = await asyncio.wait(in_flight, timeout=self._shutdown_grace_seconds)
        for task in pending:
            task.cancel()
