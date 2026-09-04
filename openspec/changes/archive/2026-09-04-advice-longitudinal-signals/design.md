## Context

`calobot.reporting.aggregation` already builds one period's totals
(`build_food_report`, `build_weight_report`, `build_activity_report`), each taking a
`period`, a `reference_day` and a timezone, and computing `[start, end)` via
`period_bounds_utc`. `calobot.advice.tools` wraps each of those in a read-only tool
with `user_id`/`tz` closed over at registry construction (see proposal.md - Why).
There is no notion anywhere of "the period immediately before this one", and no
derived behavioural measure beyond what a report already renders.

## Goals / Non-Goals

**Goals:**
- One deterministic aggregator that computes the previous period adjacent to a given
  period/reference_day, and diffs calories, weight and activity against it using the
  exact same per-period computations the reports use.
- Three derived signals (logging consistency, meal-timing drift, calorie-density
  trend), each with its own stated minimum amount of data, computed from raw entries
  rather than narrated.
- One new read-only advice tool exposing all of the above as a single retrieval.

**Non-Goals:**
- No new report, chart, or user-visible command — this only feeds the advice agent.
- No storage of the comparison or the signals; both are computed fresh on every call.
- No macro-nutrient signal (see proposal.md - What Changes).

## Decisions

**Previous-period boundary computed directly, not via a synthetic "previous reference
day" fed back through `period_bounds_utc`.** For `day` and `week`, subtracting 1 or 7
days from `reference_day` and calling `period_bounds_utc` again would work, but for
`month` and `year` an equivalent trick (e.g. `reference_day.replace(month=...)`) risks
an invalid date (Mar 31 → Feb 31) or a leap-year mismatch (Feb 29 → non-leap year - 1).
Instead, a small `_previous_period_start` derives the previous period's start date
directly from the *current period's own start date* (always day 1 of the month for
`month`, Jan 1 for `year`, the Monday for `week`), where subtracting a month/year is
always a valid date by construction. The previous period's end is exactly the current
period's start, so the two periods are adjacent with no gap or overlap by construction,
not by a check.

**Comparison reuses `build_food_report` / `build_weight_report` / `build_activity_report`
for both periods rather than a bespoke query.** This is the load-bearing choice behind
the proposal's "cannot disagree with a report" requirement: the comparison's current-
period average calories, weight change and activity minutes are computed by calling the
same functions a report calls, once with `reference_day` and once with the previous
period's own reference day. The alternative (a dedicated SQL aggregation for the delta)
would be a second implementation of the same arithmetic that could drift from the report
path over time.

**The three behavioural signals are new code, not derived from the report
dataclasses**, because none of `FoodReport`/`WeightReport`/`ActivityReport` exposes
per-day meal times or per-entry grams — they already discard that detail once they've
produced a total. Each signal function takes the raw entries for a period (already
`deleted_at`-filtered by `get_entries_in_range`) and computes its own measure:
- **Logging consistency**: `days_with_food_logged / days_elapsed_in_period` (elapsed
  clipped to `today_local()`, matching `days_with_no_data`'s existing convention).
- **Meal-timing drift**: the median local hour of each day's last logged meal, then the
  difference between the current and previous period's median.
- **Calorie-density trend**: total kcal / total grams × 100 for the period (entries
  with `grams is None` excluded, since density needs a mass to divide by), labelled
  `"in aumento"` / `"in calo"` / `"stabile"` against the previous period at a ±5%
  band, `None` when the previous period itself lacks enough data to trend against.

**A single per-signal minimum-data constant (`MIN_DAYS_FOR_SIGNAL = 3`), not a
tuned threshold per signal.** All three signals need multiple distinct days to mean
anything at all (one day cannot show "drift" or "consistency"); a single small
constant is easier to reason about and to state to the user consistently ("servono
almeno 3 giorni di dati") than three independently-tuned numbers that happen to select
similar behaviour today. `enough_data` is evaluated against the *current* period only —
the previous period failing the same bar degrades that specific delta/trend field to
`None` without invalidating the current-period value, since "how are you logging this
week" can be worth reporting even when last week had no data at all.

**One aggregator function, `build_period_comparison`, returns a single dataclass with
the comparison plus the three signals**, rather than four separate functions the tool
handler would need to call and assemble. The proposal describes one tool
(`get_period_comparison`) over one coherent concept ("what's different"); splitting the
aggregation into four calls would just move the assembly into the tool handler for no
gain, since nothing else in the codebase needs the signals independently of the
comparison.

## Risks / Trade-offs

- **A ±5% density band and a 3-day minimum are judgement calls, not derived from
  data.** They are simple enough to name in a scenario and to defend if wrong;
  revisiting them later (per proposal.md - Non-goals, no storage) costs nothing beyond
  editing a constant, since nothing depends on today's exact threshold.
- **Meal-timing drift uses the *last* meal's hour only**, not a full-day timing
  profile, matching the dietician review's existing notion of "typical hour of the
  last meal" referenced in proposal.md - Why, rather than inventing a second timing
  measure the review doesn't use.
