## Why

Today's daily calorie budget (`target_kcal`) is TDEE from BMR times a fixed
lifestyle-activity multiplier chosen once in the profile (`sedentario` ...
`molto_attivo`), representing *typical* activity. Logged workouts are shown
only as a separate, informational figure and are explicitly never folded into
the budget or the "differenza" (`specs/reporting` - Activity report contents:
"never as an adjustment to the calorie budget"). On a day where a user does
meaningfully more than their typical level - e.g. a real case observed on
2026-08-23: 944 kcal eaten, budget 1929 kcal, differenza -986, while the same
day also logged ~890 kcal burned across two walks - the reported deficit
understates true energy balance by roughly the activity kcal, which can read
as "doing great, eat less" on exactly the day the user has earned room to eat
more. This proposal reverses that earlier decision for the **day** period only,
adding back a capped share of that day's logged activity kcal before computing
the budget comparison, while leaving week/month/year reporting as pure
information (multi-day activity levels are already smoothed into the profile's
lifestyle multiplier, so daily re-injection does not extend cleanly to longer
periods).

This change also adds forward-looking and habit-level advice to reports,
tiered by period: a day report is not just a scorecard for a day that is
still happening, and a month/year report is currently limited to the same
single "actionable recommendation" the week report gets, with no explicit
treatment of macronutrient balance.

## What Changes

- Add a bounded "activity credit" added to the day's effective budget before
  computing `difference_kcal` (day period only) in
  `calobot.reporting.aggregation.build_food_report`, and to
  `remaining_today_kcal` in `calobot.advice.tools._profile_and_budget_handler`.
- The credit is a fraction of that day's `ActivityReport.total_kcal` (default
  50%), capped at an absolute per-day maximum, to offset the known tendency of
  LLM-estimated activity kcal to run high - never a 1:1 add-back.
- Week/month/year calorie reports and their `difference_kcal`/average
  comparisons are unchanged: activity stays purely informational there, per
  the existing requirement.
- The calorie report text and chart for the day period gain a visible mention
  of the activity credit actually applied, so the adjusted budget is never
  silently different from the profile's stated `daily_budget_kcal`.
- **BREAKING** (behavioral, not API): the daily "budget"/"differenza" figures
  in `Report giornaliero`, `/profilo`-adjacent tools, and
  `get_calorie_summary`/`get_profile_and_budget` advice-agent tool outputs for
  the `day` period will differ from before on any day with logged activity.
- Add tiered advice to reports, generated the same LLM-driven way the existing
  week/month dietician review is (see `specs/dietician-reviews`), and subject
  to the same guardrail already in the bot's prompts that Calobot does not
  track macronutrients as structured data (`src/calobot/reporting/dietician.py`,
  `src/calobot/advice/agent.py`) — the advice reasons about protein/fat/carb
  *balance* qualitatively from food descriptions, the same way the existing
  density insight reasons from kcal/100g without a stored density field, and
  never states a specific gram amount of a macronutrient:
  - **Day report**: advice for the rest of the day, informed by the (now
    activity-credited) remaining calories and a qualitative read of whether
    what has been eaten so far leans toward one macronutrient group, so the
    suggestion nudges towards balance (e.g. "resta spazio per una fonte
    proteica stasera").
  - **Week report**: advice for the rest of the week, replacing the current
    single generic "actionable recommendation" for the week period with one
    framed around the days remaining in the week and the week's calorie/
    balance trend so far.
  - **Month/year report** ("general report"): advice on general habits to
    adopt for health, replacing the current single "actionable recommendation"
    for these periods with a fuller habits-oriented note that explicitly
    addresses macronutrient balance (protein, fat, carbohydrate variety) in
    addition to the density/timing/provenance observations already made.
  - Day-period advice is new (today's report is text-only with no dietician
    review, since the existing minimum period for a review is a week); week
    and month/year advice replace, rather than add to, the existing single
    actionable recommendation in the same schema slot.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `reporting`: day-period calorie report contents now factor in a capped
  share of the day's logged activity kcal when computing the budget
  comparison; the "never as an adjustment" wording is narrowed to
  week/month/year periods. The day report additionally gains a
  rest-of-day advice line.
- `dietician-reviews`: the single "actionable recommendation" slot in the
  structured review is now tiered by period — a rest-of-week recommendation
  for the week period, and a general-habits recommendation covering
  macronutrient balance for month/year periods — instead of one
  undifferentiated recommendation for every period of a week or longer.

`advice-agent`'s existing requirement ("Reported figures come from
deterministic computation") already binds `remaining_today_kcal` to whatever
the shared reporting computation produces, so it needs no requirement change -
`_profile_and_budget_handler` will simply call the same updated computation.
The advice-agent's separate "Reported figures..." requirement is unaffected
since advice text is prose, not a stated figure, and the agent already may
answer with a dietician review outside a report per
`specs/dietician-reviews` - Dietician review reachable outside a report.

## Impact

- `src/calobot/reporting/aggregation.py` (`build_food_report`, day branch) -
  needs the day's `ActivityReport.total_kcal` as an additional input.
- `src/calobot/advice/tools.py` (`_profile_and_budget_handler`) - same credit
  applied to `remaining_today_kcal`.
- `src/calobot/ingestion/pipeline.py` (~lines 974-1041) - day-period report
  text/chart wiring; must pass activity kcal into `build_food_report` and
  surface the credit applied in the reply text; day-period branch gains a
  call to generate rest-of-day advice.
- `src/calobot/profile/budget.py` - no change to `compute_budget`/`BudgetResult`
  itself; the credit is applied at the reporting layer, keeping `target_kcal`
  a stable, storable-if-needed figure.
- `src/calobot/reporting/dietician.py` - new day-period, lightweight
  "rest of day" advice generation (below the week-minimum threshold that
  gates the full structured review); existing structured review's single
  recommendation field becomes period-aware (week vs month/year framing).
  The module's existing "Calobot does not track macronutrients" disclaimer
  is preserved — the LLM prompt keeps that constraint and is only asked to
  reason qualitatively about balance from descriptions.
- Tests in `tests/` covering daily report text, the advice-agent budget tool,
  the calorie chart's reference line for the day period, and the new/changed
  advice content for day, week and month/year reports.
