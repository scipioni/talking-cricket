## Why

The bot's newest and riskiest value is temporal: advice memory, longitudinal signals and the
proactive nudge cycle all unfold over days. The simulation harness already controls simulated
time (a step carries an instant, and the clock seam can cross midnights), but no scenario
exercises that reach: every expectation judges the bot's reply to a step, a nudge is a message
the bot originates *between* steps, and a broken-streak signal requires days in which the user
sends nothing at all — a span the scenario vocabulary cannot express. The class of failure that
matters most ("user received four nudges in one afternoon", "opt-out ignored on day 2") is
invisible to single-turn tests and has never been watched unfold.

## What Changes

- Make **silence a first-class scenario element**: a step type that advances time across one or
  more days with no user message, so signals that require an absent user (broken streak, goal
  reached, aged unresolved suggestion) can fire inside a run.
- Have the harness **drive scheduled jobs while time advances** — at minimum the nudge cycle —
  so the temporal behaviours the scheduler owns occur inside the simulation rather than only in
  unit tests that call the cycle directly.
- Add **expectation types for originated messages**: that a nudge of a given kind arrives, and
  that none arrives, scored the way existing expectations are scored.
- Add **temporal invariants** checked after every action: at most one nudge per user per rate
  window, never outside the allowed hours, never while nudges are disabled or no-retention is
  on, none after an opt-out, and no nudge about a suggestion whose outcome is already resolved.
- Keep live runs bounded as today: new scenario kinds declare their model-call budget like any
  other, and the default suite stays offline.
- One latent defect in `src/calobot/nudges/` this work surfaced and fixes: the cycle crashed on
  every run after its first send (naive SQLite read of `last_nudge_sent_at` subtracted from an
  aware `now`), which no existing test could reach. Found by task 2.2; no behaviour beyond that
  repair changes.

**Non-goals:** no change to product behaviour — nudge selection, content limits and safety
paths are exactly as specified in `proactive-nudges`; no trajectory-scoped expectations that
judge consistency of advice across weeks (worth exploring later, not here); no new scheduling
machinery.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `conversation-simulation`: scenarios may span many simulated days, including spans of total
  silence; scheduled jobs run as part of advancing time; the expectation vocabulary and the
  post-action invariants extend to messages the bot originates (nudges) and to the temporal
  limits on them.

## Impact

- `tests/harness/` — `scenario.py` (new step and expectation types), `simulation.py`/`run.py`
  (driving the nudge cycle when time advances, scoring originated messages),
  `invariants.py` (temporal invariants over the nudge send history), `clock.py` (likely
  unchanged; it already advances).
- `src/calobot/nudges/` — read from, not changed: the cycle must be invocable the same way the
  scheduler invokes it, which it already is.
- `tests/test_live_simulation.py` and the scenario library gain at least one multi-day nudge
  scenario; unit tests and the default offline suite are unaffected.
- No schema change, no `src/calobot/` behaviour change, no migration.

## Risks

- A harness that drives real time-dependent code across days can produce flaky runs if any
  component reads the wall clock instead of the scenario instant; the existing clock seam
  (`timeutil.set_clock`) is the guard, and any violation will surface as an inexplicable
  signal — which is itself a finding worth reporting.
- Scope creep toward a full behavioural simulator (personas that decide to log or not log for
  realistic reasons, effectiveness measurement). This change deliberately stops at
  *scripted* time-lapse: deterministic days, deterministic signals.

## Dependencies

Requires nothing new: `background-scheduler`, `advice-memory`, `advice-longitudinal-signals`
and `proactive-nudges` are all implemented, and `conversation-simulation` already specifies
simulated time. This change only teaches the harness to use what exists.
