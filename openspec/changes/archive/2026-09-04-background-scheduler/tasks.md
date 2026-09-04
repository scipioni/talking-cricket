## 1. Scheduler module

- [x] 1.1 New module `calobot.scheduler` with a `Job` dataclass (`name`,
      `interval_seconds`, `func: Callable[[], Awaitable[None]]`) and a `Scheduler`
      class.
- [x] 1.2 `Scheduler.register(name, interval_seconds, func)`: raises on a duplicate
      name; only valid before `run()` starts.
- [x] 1.3 `Scheduler.run()`: tick loop; per tick, for each registered job, skip if
      its previous run task is not yet done (log the skip), otherwise launch it if
      due; catches and logs a job's exception without letting it propagate; on its
      own `CancelledError`, runs the bounded-grace-period shutdown sequence
      (design.md - Decisions) and returns cleanly.
- [x] 1.4 `enabled=False` short-circuits `run()` to a no-op immediately, per
      specs/background-scheduling - The scheduler can be disabled entirely.

## 2. Wiring

- [x] 2.1 `calobot.settings.Settings`: `scheduler_enabled: bool = True`,
      `scheduler_tick_interval_seconds: float`, `scheduler_shutdown_grace_seconds:
      float`.
- [x] 2.2 `main.py`: construct a `Scheduler` from settings, add `scheduler.run()` as
      a third `asyncio.gather` member. No jobs registered by this change
      (design.md - Non-Goals).

## 3. Tests

- [x] 3.1 A registered job runs at approximately its interval (short intervals, real
      `asyncio.sleep`, no clock injection needed at this granularity).
- [x] 3.2 Duplicate registration is rejected.
- [x] 3.3 A slow-running job's next due tick is skipped while it's still running,
      and the skip doesn't stop later ticks once the job finishes.
- [x] 3.4 A job that raises doesn't stop the scheduler or other jobs from continuing
      to run on schedule.
- [x] 3.5 Shutdown mid-run: a fast job's in-flight run is waited for; a
      slower-than-the-grace-period job's run is abandoned without hanging shutdown.
- [x] 3.6 `enabled=False` runs no job even when several are registered.
- [x] 3.7 No jobs registered: `run()` still starts and stops cleanly.

## 4. Verification

- [x] 4.1 `task check` passes (diffed against the established pre-existing
      baseline).
