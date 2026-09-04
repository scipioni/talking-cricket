## Context

`_async_main` in `calobot.main` runs exactly two concurrent tasks via
`asyncio.gather`: `dispatcher.start_polling(bot, settings=settings)` and
`server.serve()`. Long polling means a single bot instance is already implicit
(two instances would both long-poll Telegram and race for updates), but nothing
states or protects that assumption today. `telemetry_history` shows the codebase's
existing pattern for a background task: `start_listening()` creates a detached
`asyncio.Task` and stores it; `stop_listening()` cancels it. That task is *not* part
of `asyncio.gather` - it is fire-and-forget, so an explicit cancel in `main.py`'s
`finally` block is what stops it.

## Goals / Non-Goals

**Goals:**
- A `Scheduler` class: explicit job registration at startup, a tick loop, an
  overlap guard per job, per-job failure isolation, and a bounded-grace-period
  shutdown.
- Wire it as a third `asyncio.gather` member in `main.py`, unlike telemetry's
  detached-task pattern, specifically so the main task's own cancellation (on
  process shutdown) reaches the scheduler's loop directly and its shutdown
  sequence runs from inside that cancellation, not from a separate manual `.cancel()`
  call with no chance to wait for a grace period first.
- An enable/disable setting and a tick-interval setting.

**Non-Goals:**
- No cron expressions - jobs run on a fixed interval from registration, not at
  specific wall-clock times.
- No persistent job store or distributed coordination - jobs and their state live
  in process memory and reset on restart.
- No retry-with-backoff for a failing job - it simply runs again on its next due
  interval (design already covers is this is not silent: the failure is logged).
- No jobs registered by this change - `proactive-nudges` registers the first one.

## Decisions

**The scheduler's `run()` coroutine is a direct member of `asyncio.gather` in
`main.py`, not a detached task like `telemetry_history`.** This is the one place
this change deviates from copying the existing pattern verbatim, and deliberately
so: `telemetry_history`'s task is fire-and-forget specifically because nothing needs
to *wait* for it to wind down - a hard cancel is fine for a pure in-memory event
collector. The scheduler needs the opposite: when the process is shutting down, an
in-flight job run may be mid-write to the database, and simply cancelling the task
gives it no chance to finish within a grace period. Making `run()` a `gather`
member means the same cancellation that stops polling and the web server also
delivers a `CancelledError` into the scheduler's own loop, where it is caught once
and turned into the bounded-grace-period shutdown sequence - no separate explicit
call from `main.py`'s `finally` block is needed, unlike `telemetry_history.
stop_listening()`.

**A tick loop with a per-job "next due" check, not one `asyncio.sleep` timer per
job.** N independently-sleeping timers would each need their own cancellation and
overlap bookkeeping; a single loop that wakes every `tick_interval_seconds` and asks
each job "are you due, and are you still running from last time" keeps all of the
overlap/failure/shutdown logic in one place, at the cost of a job's actual run
being delayed by up to one tick after its interval elapses. This project has no job
whose timing precision matters at the sub-tick level, and it is proactive-nudges'
own job (not this change's) that will decide how large its interval needs to be
relative to the tick.

**Overlap tracking is one `asyncio.Task | None` per job name, checked with
`.done()`.** The simplest possible representation of "is this job currently
running" that also lets shutdown find in-flight tasks to wait on, with no extra
locking: a tick loop and its own job-launching code run on the same event loop
thread, so there is no race between checking `.done()` and launching a new run.

**A fixed grace period, not a per-job one.** The proposal's non-goals already
exclude persistent job stores and distributed coordination; a per-job override
would be one more knob nothing in this codebase yet needs, since `proactive-nudges`
(the only planned job) does nothing that benefits from a longer grace period than
any other periodic write.

**Single-instance safety is documentation plus a design property, not a lease.**
The proposal frames "document safety under violation, or take a lease" as the
central decision. A lease needs a schema change and a place to store it - real cost
for a project whose deployment model (long polling, one container) already implies
one instance, and where every job this scheduler is expected to run in the
foreseeable future (`proactive-nudges`'s rate-limited, idempotent send-or-stay-
silent cycle) tolerates running twice as often under an accidental second instance
without corrupting anything or double-messaging a user beyond what a more
aggressive interval could already do on a single instance. A lease is worth adding
the day a job is proposed that would not tolerate that.

## Risks / Trade-offs

- **A tick-based loop introduces up to one tick of scheduling jitter.** Acceptable
  given the Non-Goals above; `tick_interval_seconds` is a setting precisely so a
  deployment can tighten it if a future job needs finer granularity.
- **The single-instance assumption is real, not enforced.** Explicitly named as a
  risk in the proposal; the mitigation is the job-level tolerance described above,
  not a technical guarantee this change provides.
