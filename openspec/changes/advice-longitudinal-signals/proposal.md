## Why

Every tool the advice agent has answers the same shape of question: *what is the value
over period P*. None answers *what is different about this period compared with how this
user usually is*. So when a user asks "sto migliorando?" or "come mi sto comportando
ultimamente?", the agent must reconstruct a delta from two separate period summaries and
describe it in prose — which is exactly the arithmetic the `advice-agent` requirement
"Reported figures come from deterministic computation" forbids it from doing.

The result is a bot that can tell you *where you are* but not *what changed about you*.
The dietician review is the only place a behavioural pattern is ever named, and it only
appears attached to a week-or-longer report — it cannot be asked a question, and it
recomputes its impressions from scratch every time.

## What Changes

- Add deterministic comparison aggregations alongside the existing period aggregations
  in `calobot.reporting`: period-over-period deltas for calories, weight and activity,
  computed the same way a report computes its totals so a comparison and a report can
  never disagree.
- Add derived behavioural signals that are computed, not narrated: logging-consistency
  (days logged out of days in period), meal-timing drift (typical hour of the last meal,
  and how it moved), and calorie-density trend. Each is a number or a labelled category
  produced by code.
- Add a `get_period_comparison` read-only tool to the advice agent exposing those deltas
  and signals, so "sto migliorando?" is answered from a computed comparison rather than
  from the model subtracting two totals it was shown.
- State explicitly, per signal, how much data it needs before it means anything, and
  return "not enough data" rather than a weak signal — the existing "Too little data to
  support the answer" scenario currently has no deterministic backing.
- Keep every signal qualitative-or-counted only. No macronutrient claim becomes possible
  here, since the system still does not track macronutrients.

**Non-goals:** no new user-visible command, no change to what reports render, no
storage of computed signals (they are derived on read, like every existing report).

## Capabilities

### New Capabilities

None. This deepens what the advice agent can be asked, using the aggregation layer that
already exists.

### Modified Capabilities

- `advice-agent`: gains a requirement that a comparison between periods, and any
  behavioural pattern the answer asserts, is produced by deterministic computation
  rather than by the model comparing retrieved figures; and that a signal with too
  little data behind it is reported as such rather than stated weakly.

## Impact

- `src/calobot/reporting/aggregation.py` — new comparison and signal aggregations
  beside the existing `build_*_report` functions.
- `src/calobot/advice/tools.py` — one new read-only tool wrapping them.
- `src/calobot/advice/agent.py` — gather prompt mentions the new tool.
- `tests/` — new aggregation tests; advice tests for the comparison path.
- No database schema change, no migration, no new dependency.
- Every read path must keep filtering `deleted_at`, as the existing aggregations do.

## Dependencies

None. This is the first of three related changes (`advice-memory` and
`proactive-nudges` follow) and is the only one of the three that is independently
useful on its own.
