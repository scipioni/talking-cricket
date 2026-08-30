## Why

Nothing in the bot happens unless a user sends a message. `main.py` runs exactly two
concurrent tasks — long polling and the telemetry web server — and there is no way to
say "run this every N minutes". `proactive-nudges` needs one, and so would any future
retention pruning, cache expiry or scheduled export.

Building that machinery inside `proactive-nudges` would mix two unrelated kinds of
requirement in one spec: *when may the bot message a user* and *how does a periodic task
avoid double-firing*. Separating them keeps each spec about one thing, and leaves the
scheduling behaviour testable without involving a single user-facing message.

## What Changes

- Add an in-process scheduler: a third task in the existing `asyncio.gather`, built on
  plain `asyncio` with **no new dependency**. The project's fifteen direct dependencies
  each earn their place, and one periodic job does not justify a scheduling library.
- Let application code register a named job with an interval. Registration is explicit
  and happens at startup, so what runs on a timer is readable in one place.
- Never overlap a job with itself: if a run is still going when the next is due, the due
  run is skipped and the skip is logged, rather than queuing runs that pile up.
- Isolate failures: a job that raises is logged with its traceback and the scheduler
  keeps running. One broken job SHALL NOT stop the others, and SHALL NOT stop the bot —
  the scheduler task must never be the reason polling dies.
- Shut down cleanly: on shutdown, stop scheduling new runs and let an in-flight run
  finish within a bounded grace period, following the cancellation pattern
  `telemetry_history.stop_listening()` already establishes.
- Make the whole thing switchable off by configuration, so a deployment (or a test run)
  can start the bot with no background work at all.
- Address multi-instance safety explicitly. Long polling means a single instance is
  implicit today, but nothing states it. Either the scheduler documents that it assumes
  one instance and behaves safely if that is violated, or it takes a lease — this is the
  central design decision and the reason this change exists separately.

**Non-goals:** no cron expressions, no persistent job store, no distributed
coordination, no retries with backoff, and no user-visible behaviour of any kind. This
change adds the ability to run something periodically and nothing that uses it.

## Capabilities

### New Capabilities

- `background-scheduling`: runs registered application jobs on a fixed interval inside
  the bot process, without overlapping runs, without letting a failing job take down the
  bot, and without leaving work in flight at shutdown.

### Modified Capabilities

None. No existing capability changes behaviour, and nothing a user can observe changes.

## Impact

- `src/calobot/scheduler/` (new module) — the loop, job registration, overlap guard.
- `src/calobot/main.py` — a third entry in `asyncio.gather`, and shutdown handling in
  the existing `finally` block.
- `src/calobot/config.py` — an enable/disable setting and the tick interval.
- `tests/` — scheduling behaviour is testable directly: overlap skipping, failure
  isolation, and shutdown all assert on code, with no clock left to real time.
- No database schema change unless the multi-instance decision calls for a lease.
- **No new dependency.**

## Dependencies

None. This is infrastructure and lands before `proactive-nudges`, which will register
the first job on it. Nothing else currently needs it, and this change deliberately ships
with zero jobs registered.
