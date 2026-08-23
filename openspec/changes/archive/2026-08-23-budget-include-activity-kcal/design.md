## Context

`compute_budget()` (`src/calobot/profile/budget.py`) is a pure function of
profile fields only; it has no notion of "today's" logged entries and is not
persisted, so it is recomputed on demand (see its module docstring). The
report layer (`src/calobot/reporting/aggregation.py`) already builds
`FoodReport` and `ActivityReport` for the same `(user, period, reference_day)`
side by side in the pipeline's day-report branch
(`src/calobot/ingestion/pipeline.py` ~974-1041) and in
`advice/tools.py::_profile_and_budget_handler`. Both call sites already have
everything needed to compute an activity credit; no new query or stored state
is required. See proposal.md - Why for the motivating gap.

The existing dietician review (`src/calobot/reporting/dietician.py`) already
runs one `LLMGateway.call_structured` call with a flat `DieticianReview`
schema, gated on `period >= week` and >= 3 distinct logged days, whose system
prompt already tells the model explicitly that Calobot does not track
macronutrients and to reason only from indirect signals (density, timing,
variety, provenance). Nothing in this change touches that constraint - the
new/changed advice text stays within it. Neither `FoodEntry` nor any other
model stores protein/fat/carb grams (confirmed: no such columns exist,
`food-logging` spec has no macronutrient requirement), so "macronutrient
balance" advice is necessarily the same kind of qualitative, description-based
reasoning the density insight already does, not a computation over stored
values.

## Goals / Non-Goals

**Goals:**
- Make the day-level "differenza" reflect that exercise increases the day's
  effective allowance, without trusting self-reported/LLM-estimated activity
  kcal at face value.
- Keep the change local to the reporting layer: `BudgetResult`/`target_kcal`
  stays a pure profile-derived figure, so anything that reads "the budget"
  elsewhere (chart reference line default, `/profilo` display) is unaffected
  unless it explicitly asks for the day's adjusted figure.
- Keep week/month/year reports byte-for-byte unchanged.

- Add rest-of-day, rest-of-week, and general-habits advice to reports without
  ever having the model claim a specific macronutrient gram amount, since none
  is tracked.

**Non-Goals:**
- Changing `compute_budget()` or `ACTIVITY_FACTORS` (the profile-level
  lifestyle multiplier) - that remains the "typical day" baseline.
- Building a per-activity-type credibility model (e.g. trusting "camminata"
  more than "corsa"). The cap is a single flat fraction/ceiling for now.
- Persisting the credited amount; it is recomputed on read, same as the
  budget itself.
- Adding macronutrient tracking (new columns, LLM extraction of protein/fat/
  carbs). Advice reasons qualitatively from descriptions and density, exactly
  like the existing density insight - this is a documentation/prompt-scope
  change, not a data model change.

## Decisions

**Credit formula: `credit = min(0.5 * activity_kcal_today, CREDIT_CAP_KCAL)`.**
- Why 50%: logged activity kcal already goes through an LLM
  estimate-then-lookup path (per AGENTS.md's note on structured-extraction
  degradation risk) with no wearable ground truth, and MET-based activity
  kcal formulas are widely known to run 20-40% high for self-reported
  duration/intensity. Splitting the difference at 50% avoids encouraging
  overeating on the strength of an inflated estimate while still visibly
  fixing the reported case (890 kcal logged -> 445 kcal credited, budget
  1929 -> 2374, differenza -986 -> -430, still a deficit but no longer an
  implausible one).
- Why a flat cap instead of a percentage-of-TDEE cap: simpler to explain in
  the report text ("credito attività: +X kcal, tetto Y kcal") and independent
  of profile fields that can change (weight, goal). Proposed
  `CREDIT_CAP_KCAL = 600`, a level picked to still allow crediting genuinely
  long endurance days while blocking runaway single-entry estimation errors;
  this is a tunable constant, not a hard product decision, and can move
  without a spec change since the spec states "capped at a fixed absolute
  maximum" rather than a number.
- Alternative considered: 1:1 credit, no cap. Rejected - directly amplifies
  LLM overestimation risk into a bigger reported allowance, the opposite of
  the safety-floor philosophy already used for `FLOOR_KCAL` deficits.
- Alternative considered: per-activity-type multipliers (trust cardio less
  than logged steps, etc). Rejected as unnecessary complexity for the size of
  the gap being closed; can be revisited later without touching this spec's
  wording (still "a fixed fraction... capped").

**Where the credit is computed: a new small pure function next to
`build_food_report`, e.g. `activity_credit_kcal(activity_kcal: float) -> float`
in `aggregation.py`, taking a plain float rather than an `ActivityReport` so it
has no dependency on the DB session.** `build_food_report`'s day branch calls
`build_activity_report` for the same `(user, "day", reference_day)` args it
already effectively has available at both call sites, and passes
`total_kcal` in as a new optional parameter.

- Why not inside `compute_budget()`: that function is profile-only and has no
  session/entries access; keeping it that way preserves its "pure,
  recomputed automatically" property for `specs/user-profile`.
- Why not a wrapper `BudgetResult` field: would need the caller to already
  have both `BudgetResult` and today's activity entries merged, which is
  exactly what the two call sites in `aggregation.py`/`tools.py` are for;
  putting it in `aggregation.py` keeps one implementation shared by both.

**API shape:** `build_food_report(..., budget_kcal, *, activity_kcal_today: float = 0.0)` for the day branch only (ignored for other periods, or asserted unused - non-day callers simply omit it). `_profile_and_budget_handler` fetches `build_activity_report(..., "day", ...)` alongside its existing `build_food_report` call and passes `total_kcal` through.

**Report text:** the day-report line in `pipeline.py` gains the credited
amount only when non-zero, e.g. `"... (budget 1929 kcal + 445 credito
attività, differenza -430)"`, keeping the no-activity case's text identical
to today's.

**Week/month/year advice: tier the existing single `actionable_tip` field
instead of adding new schema fields.** `build_dietitian_review` gains a
`period: Period` parameter; `DIETICIAN_SYSTEM_PROMPT` gains a short
period-conditional instruction block appended at render time (two fixed
string variants, chosen in Python, not left to the model to infer from
`period`) telling the model whether `actionable_tip` should be framed as
"cosa fare nei giorni rimanenti di questa settimana" (period == "week") or as
a general habit recommendation that explicitly touches protein/fat/carb
variety qualitatively (period in {"month", "year"}). The `DieticianReview`
schema itself, its other four fields, and the `>= 3 distinct days logged`
gate are unchanged.
- Why reuse the field instead of adding `weekly_tip`/`general_habit_tip`
  fields: the schema stays flat per AGENTS.md's LLM-gateway convention
  (small flat Pydantic schema per call); only one of the two framings is ever
  relevant for a given call, so a second optional field would just be null
  half the time for no benefit.
- Why a Python-selected prompt variant instead of asking the model to look at
  `period` itself: keeps the tiering deterministic and testable without
  relying on the model correctly reading a period value out of the prompt
  content.

**Day-level rest-of-day advice: a new, separate, smaller LLM call, not a
reuse of `build_dietitian_review`.** The existing review requires >= 3
distinct logged days and produces 5 fields describing multi-day patterns
(timing regularity, provenance quality) that do not exist for a single day.
A new function, e.g. `build_daily_advice(gateway, entries_today,
remaining_kcal, activity_credit_kcal) -> str | None` with its own minimal
flat schema (a single `advice: str` field, or returned directly as text),
gated only on "at least one food entry logged today" (per the new reporting
scenario). Input signals: today's food descriptions (for the same
qualitative high/low-density read used elsewhere), and the already-computed
remaining credited calories - no new query beyond what the day-report branch
already has once activity credit (this same change) is wired in.
- Why not extend `build_dietitian_review` with a `period == "day"` branch:
  that function's whole signal set (`get_dietician_signals`) is built around
  multi-day aggregates (`days_logged`, `time_distribution_kcal` buckets,
  `provenance_distribution_count`) that are noisy or meaningless over a
  single day; forcing day-period through the same >= 3-day gate would also
  contradict wanting *every* day report with food logged to get advice.

## Risks / Trade-offs

- [Users game the credit by over-reporting activity duration/intensity to
  unlock more food] → the 50%/cap combination already discounts this; if
  abuse is observed in practice, the fraction/cap constants can be tuned
  without a spec change (the spec only commits to "a fixed fraction...
  capped").
- [Two near-identical computations for "today's calories" now exist -
  uncredited `target_kcal` from the profile and the credited day-report
  figure - risk of some future call site using the wrong one] → keep exactly
  one function (`activity_credit_kcal` + the day branch of
  `build_food_report`) as the sole place the credit is applied; `BudgetResult`
  itself is never mutated.
- [Chart reference line for the day period currently draws `budget_kcal`
  unmodified (`render_calorie_chart`)] → out of scope per spec (`Charts`
  requirement is unchanged), but note in tasks.md to check it does not
  desync visually from the now-different text figure for single-day charts;
  per the existing `Charts` requirement, day-period reports do not render a
  chart at all, so this is a non-issue in the current implementation but
  worth a task-list check.

- [Model drifts into stating a specific macronutrient gram amount despite
  instructions] → keep the existing hard rule already present in
  `DIETICIAN_SYSTEM_PROMPT` ("Non inventare dati o macronutrienti") and extend
  it, rather than replacing it, when adding the period-tiered instruction
  block; cover with a test asserting no digit-plus-"g" pattern next to
  protein/fat/carb words in generated advice fixtures used in tests.
- [Day-level advice call adds LLM latency/cost to every daily report with
  food logged, unlike today where day reports are LLM-free] → acceptable per
  proposal's intent (this is the point of the change), but keep the new call
  a single small flat-schema call per AGENTS.md's LLM-gateway convention, and
  make it non-fatal (falls back to no advice line, exactly like
  `build_dietitian_review`'s existing `except Exception` fallback) so an LLM
  failure never breaks the deterministic calorie figures.

## Migration Plan

No data migration - the credit is computed on read from already-stored
entries, like the budget itself. Deploy as a normal code change; no feature
flag needed since the previous behavior (zero credit) is just the `0.0`
default for `activity_kcal_today`. The advice additions are purely additive
report text and a prompt/parameter change to an existing LLM call path - no
schema migration, no feature flag.
