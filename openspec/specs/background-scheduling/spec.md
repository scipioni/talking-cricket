# background-scheduling Specification

## Purpose
Runs application jobs on a fixed interval inside the bot process, without overlapping
runs, without letting a failing job take down the bot, and without leaving work in
flight at shutdown, so a future periodic need (nudges, retention pruning, cache
expiry) has one place to register instead of inventing its own timer.

## Requirements

### Requirement: Jobs are registered explicitly at startup

The system SHALL let application code register a named job together with the
interval it should run at. Registration SHALL happen at startup, before the
scheduler begins running, so what runs on a timer is readable in one place rather
than discovered at runtime.

#### Scenario: A job is registered

- **WHEN** application startup registers a named job with an interval
- **THEN** the scheduler runs that job at approximately that interval once it starts

#### Scenario: No jobs registered

- **WHEN** the scheduler starts with no jobs registered
- **THEN** it runs without executing anything, and this is not an error

#### Scenario: Duplicate job name

- **WHEN** application startup attempts to register two jobs under the same name
- **THEN** the second registration is rejected before the scheduler starts, rather
  than silently replacing or duplicating the job

### Requirement: A job never overlaps itself

If a job's previous run is still in progress when its next run is due, the system
SHALL skip the due run rather than starting a second concurrent run of the same job,
and SHALL log that the run was skipped.

#### Scenario: Previous run still in progress

- **WHEN** a job's interval elapses while its previous run has not yet finished
- **THEN** the due run is skipped, the skip is logged, and the previous run is left
  to finish on its own

#### Scenario: Previous run already finished

- **WHEN** a job's interval elapses and its previous run finished before the
  interval elapsed
- **THEN** the job runs again

### Requirement: A failing job does not stop the scheduler or the bot

The system SHALL isolate a job's failure to that job. When a job's run raises, the
system SHALL log the error with its traceback and continue scheduling every job,
including the one that failed, on its next due interval. No job failure SHALL stop
the process the scheduler runs in.

#### Scenario: A job raises

- **WHEN** a scheduled run of a job raises an exception
- **THEN** the error and its traceback are logged, the scheduler keeps running, and
  every other registered job continues to run on schedule

#### Scenario: A failing job is retried on its next interval

- **WHEN** a job that failed on its last run becomes due again
- **THEN** it runs again rather than being permanently disabled by the earlier
  failure

### Requirement: Shutdown is bounded and clean

On shutdown, the system SHALL stop scheduling new job runs. If a job run is in
flight when shutdown begins, the system SHALL allow it to finish within a bounded
grace period before the process exits, and SHALL NOT allow an in-flight run to block
shutdown indefinitely.

#### Scenario: Shutdown with no job in flight

- **WHEN** shutdown begins and no job is currently running
- **THEN** the scheduler stops immediately

#### Scenario: Shutdown with a job in flight that finishes in time

- **WHEN** shutdown begins while a job is running, and that run finishes within the
  grace period
- **THEN** the scheduler waits for it to finish before completing shutdown

#### Scenario: Shutdown with a job in flight that does not finish in time

- **WHEN** shutdown begins while a job is running, and that run has not finished by
  the end of the grace period
- **THEN** the scheduler stops waiting and completes shutdown regardless

### Requirement: The scheduler can be disabled entirely

The system SHALL support starting with the scheduler disabled by configuration, in
which case no registered job ever runs and no background task for the scheduler is
started.

#### Scenario: Scheduler disabled

- **WHEN** the bot starts with the scheduler disabled by configuration
- **THEN** no registered job runs, however many are registered

### Requirement: Single-instance assumption is stated and safe under violation

The system SHALL document that it assumes a single running instance of the bot
process, consistent with the existing single-instance assumption implied by
Telegram long polling. Running two instances SHALL NOT corrupt data or duplicate a
job's externally-visible effect beyond what running the job twice as often would
already do; at worst, a job simply runs twice as often as intended.

#### Scenario: A second instance is started by mistake

- **WHEN** two instances of the bot process run at the same time, each with its own
  scheduler
- **THEN** jobs run more frequently than intended but no job's data is corrupted or
  double-applied in a way a single, more-frequent instance could not also produce
