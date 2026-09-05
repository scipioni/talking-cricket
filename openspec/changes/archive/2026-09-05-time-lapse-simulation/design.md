## Context

The harness (`tests/harness/`) already owns a clock seam: `harness/clock.py` sets `timeutil.set_clock` per step, and `Step.at` places an action at any instant. What it cannot express is the absence of the user — every expectation judges a reply to an inbound action — nor anything about the nudge cycle, which today is only exercised by unit tests that call `run_nudge_cycle` directly. See proposal.md — Why for motivation.

Facts that constrain the design:

- `Scheduler.run` is a real asyncio loop on wall-clock `loop.time()` with no clock seam. The job is registered in `main.py` as `scheduler.register("proactive_nudges", settings.nudge_check_interval_seconds, lambda: run_nudge_cycle(bot, settings))` — an interval, not a cron.
- `run_nudge_cycle(bot, settings)` takes a `Bot`; the harness already has `FakeBot(Bot)` capturing every send as a `SentMessage` with decodable reply keyboards.
- Nudge texts are fixed Italian templates keyed by kind (`nudges/messages.py`), and nudge messages carry the stop-nudge keyboard. The cycle makes no language-model calls: signals are deterministic queries, composition is templating.

## Goals / Non-Goals

**Goals:**

- A scenario can span weeks, including spans of total silence, and judge what the bot originated.
- Nudge behaviour over time — rate window, quiet hours, opt-out, no-retention — is checked by invariants inside a run, not only by isolated unit tests.
- At least one multi-day scenario runs fully offline in the default suite.

**Non-Goals:**

- No change to `src/calobot/` behaviour; the product code is read, not edited.
- No simulation of scheduler internals (tick loop, shutdown grace) — separately unit-tested, deliberately not re-tested here.
- No trajectory-scoped expectations across steps (advice consistency across weeks) — deferred per the proposal.
- No behavioural personas that decide to log for simulated-psychological reasons; spans are scripted, deterministic.

## Decisions

### 1. Silence is its own step type, not an intent

A `Silence` step carries an end instant and an originated-message expectation, and no intent at all. Alternatives: a sentinel intent string ("__silence__") was rejected because intents are defined as what the user means and silence means nothing; a nullable `intent` field on the existing `Step` was rejected because dispatching on the type is clearer than dispatching on a null field, and the two step kinds have disjoint fields (no tap, no behaviour, no persona repertoire in silence).

### 2. Execution points are computed arithmetically; the job body is invoked directly

For each silent span (and any gap between actions), the harness computes the points `t0 + k·interval` it crosses from the run's origin and the configured `nudge_check_interval_seconds`, and calls `run_nudge_cycle(fake_bot, settings)` once per point, in order. Alternatives: driving the real `Scheduler` was rejected because its loop reads wall-clock `loop.time()` with no seam, and wrapping asyncio timing in a fake adds nondeterminism to guard against exactly the class of bug this change is meant to catch; stepping the clock hour by hour and triggering on elapsed intervals was rejected as an equivalent result with more moving parts — arithmetic crossing is exact, ordered, and cannot miss a point. The hourly default means a 30-day span crosses ~720 executions; against the in-memory SQLite session each execution is a handful of queries, which is fast enough — and the quiet-hours guard is naturally exercised because hourly points land at night too.

### 3. Nudges are identified by their observable surface

A `SentMessage` is a nudge iff it carries the stop-nudge keyboard (already decodable via `decode_options`); its kind is read by matching the fixed template owned by `nudges/messages.py` (prefix match on the stable first line, tolerant of interpolation). Attribution to the cycle is by construction: messages produced between the harness's cycle calls and its actions are delimited by call boundaries on the shared `FakeBot` stream, with monotonic message ids. Alternatives: tagging originated messages with hidden metadata through product code was rejected — it changes product code for the sake of tests; a separate send path for nudges was rejected because the design deliberately routes nudges through the same `Bot.send_message` as everything else. The coupling to template wording is accepted and bounded: a wording change edits one constant in the harness, and the match failing loudly (expectation can never be satisfied) is a better failure mode than silent misidentification.

### 4. Temporal invariants combine database state with the run's recorded timeline

Pure database checks run after every action and every cycle execution: at most one nudge per `nudge_min_interval_days` (from `last_nudge_sent_at`), quiet hours at each recorded send instant, `nudges_enabled` and no-retention at send time, and no nudge about an advice record whose outcome is resolved. Two checks need history the database does not keep — "no nudge after an opt-out earlier in the same run" — so the harness records its own timeline of enable/disable events and originated messages and checks over that. This mirrors the existing invariant architecture (`ALL_INVARIANTS`, violation fails the run with attribution to the causing action), extended with job executions as first-class causes.

### 5. One multi-day scenario runs fully offline in the default suite

The cycle is LLM-free, so a scenario whose state is seeded directly (user with nudges enabled, prior food entries establishing a streak, an old unresolved advice record) and whose only live interactions are commands and taps — which bypass classification — needs no model access. It runs in the default suite as a regression net for every temporal guard. Free-form multi-day scenarios (conversational logging across days) still contact the model, declare a call budget, and stay opt-in like all live runs. Alternatives: live-only time-lapse was rejected because it would leave the temporal invariants unexercised by `task test`, which is where regressions are actually caught; seeding everything with no interaction at all was rejected because the opt-out-honoured path needs a real conversational opt-out.

## Risks / Trade-offs

- [Template matching couples the harness to nudge wording] → match on the stable first line only; a wording change breaks loudly at the constant, never silently.
- [Arithmetic crossing assumes interval-based scheduling] → if the job ever moves to cron semantics, the crossing computation must change with it; the assumption is documented where the computation lives.
- [Hourly execution points make long spans accumulate many cycle calls] → measured cost is trivial against in-memory SQLite; scenarios that don't need a month use shorter spans rather than a reduced cadence, so the real settings are always what's tested.
- [Two invariants live only in the harness's timeline, not the database] → acceptable: the run is the unit of verification, and the database cannot record what it never observed; the timeline is written to the run report so a failure is reproducible from the report alone, as the findings requirement demands.
- [Silence spans interact with draft expiry] → a span longer than the inactivity period expires any open draft; this is already specified and implemented behaviour, and the new scenarios must expect it rather than fight it.
