## 1. Activity credit computation

- [x] 1.1 Add `CREDIT_FRACTION = 0.5` and `CREDIT_CAP_KCAL = 600` constants and an `activity_credit_kcal(activity_kcal: float) -> float` pure function in `src/calobot/reporting/aggregation.py`, and verify a unit test covers below-cap, at-cap, above-cap, and zero inputs
- [x] 1.2 Add an `activity_kcal_today: float = 0.0` keyword parameter to `build_food_report`, applied only in the `period == "day"` branch (`difference = total - (budget_kcal + activity_credit_kcal(activity_kcal_today))`), leaving the non-day branch untouched, and verify a unit test shows a day-period difference shrinking by the expected credited amount while a week-period difference for the same data is unchanged
- [x] 1.3 Extend `FoodReport` with an `activity_credit_kcal: float` field (0.0 when not applicable) so callers can render the credited amount without recomputing it, and verify existing `FoodReport` construction sites are updated

## 2. Wire the credit into call sites

- [x] 2.1 In `src/calobot/ingestion/pipeline.py`'s day-report branch (~974-1041), fetch the day's `ActivityReport` before calling `build_food_report` and pass its `total_kcal` as `activity_kcal_today`, and verify the daily `Report giornaliero` reply text includes "+N credito attività" when the credit is non-zero and is unchanged (byte-for-byte) when it is zero
- [x] 2.2 In `src/calobot/advice/tools.py::_profile_and_budget_handler`, fetch the day's `ActivityReport` and pass its `total_kcal` into the `build_food_report` call so `remaining_today_kcal` reflects the same credit, and verify a test asserts `remaining_today_kcal` increases by the credited amount on a day with logged activity
- [x] 2.3 Verify week/month/year report call sites (`build_food_report` calls for non-day periods in `pipeline.py` and `advice/tools.py`) are left passing no `activity_kcal_today` argument, and confirm via test that their output is identical to before this change
- [x] 2.4 In `src/calobot/advice/tools.py::_calorie_summary_handler` (backs the `get_calorie_summary` tool), fetch the day's `ActivityReport` and pass its `total_kcal` into `build_food_report` only when `args.period == "day"`, so `difference_kcal`/`budget_kcal` match the daily report and `_profile_and_budget_handler`, and verify a test asserts the day-period summary's `difference_kcal` includes the credit while week/month/year summaries are unchanged

## 3. Spec and documentation consistency

- [x] 3.1 Confirm the day-period calorie chart is never rendered (per the existing `reporting` Charts requirement - single-day reports are text-only), and if that assumption is ever violated by a future change, note that the chart's reference line would also need the credit

## 4. Tiered week/month/year dietician recommendation

- [x] 4.1 Add a `period: Period` parameter to `build_dietitian_review` (`src/calobot/reporting/dietician.py`) and append one of two fixed instruction blocks to `DIETICIAN_SYSTEM_PROMPT` at call time: a rest-of-week framing for `period == "week"`, a general-habits-with-macro-balance framing for `period in ("month", "year")`, and verify a unit test asserts the correct block is present in the system prompt sent to the gateway for each period
- [x] 4.2 Update the `actionable_tip` field description on `DieticianReview` and the prompt's existing "Non inventare dati o macronutrienti" rule so the macro-balance framing stays qualitative (no specific gram amounts), and verify a test on stubbed LLM output rejects/flags a fixture containing a digit-plus-"g" pattern next to protein/fat/carb words
- [x] 4.3 Update every caller of `build_dietitian_review` to pass the report's `period`, and verify existing week/month report tests still pass with the new required parameter

## 5. Rest-of-day advice

- [x] 5.1 Add a `build_daily_advice(gateway, entries_today, remaining_kcal, activity_credit_kcal) -> str | None` function in `src/calobot/reporting/dietician.py` (or a new sibling module) with its own minimal flat schema, gated on at least one food entry logged that day, non-fatal on LLM error (falls back to `None`, no advice line) matching `build_dietitian_review`'s existing exception handling, and verify a unit test covers: no entries -> `None`, LLM success -> advice string, LLM error -> `None`
- [x] 5.2 Wire `build_daily_advice` into the day-report branch of `src/calobot/ingestion/pipeline.py` (~974-1041), passing today's food entries and the activity-credited remaining calories from task 1-2, appended to the daily report reply text, and verify the `Report giornaliero` reply includes the advice line when food was logged that day and omits it when not
- [x] 5.3 Verify the day-report reply text with no advice generated (no food logged, or LLM failure) is unaffected beyond the credit text from tasks 1-2

## 6. Tests

- [x] 6.1 Add/update tests in `tests/` for `build_food_report`'s day-branch credit behavior (zero activity, below cap, above cap)
- [x] 6.2 Add/update a test for the daily report text in the ingestion pipeline showing the credited amount and the rest-of-day advice line
- [x] 6.3 Add/update a test for `get_profile_and_budget`'s `remaining_today_kcal` with and without logged activity that day
- [x] 6.4 Add/update tests for the tiered `actionable_tip` framing (week vs month/year) in the dietician review
- [x] 6.5 Run `task check` (test, lint, typecheck) and confirm it passes: `task check` was already failing on `main` before this change (50 pre-existing lint errors across untouched files, 4 pre-existing mypy errors, and one `test_memory_control.py` test that fails in this sandbox because `/data` isn't writable). This change introduces zero new lint errors, one new mypy error of the same pre-existing kind as an adjacent untouched line (`get_entries_in_range`'s union return type not narrowed - `build_daily_advice` now hits it the same way `build_dietitian_review` already did), and the full test suite passes (442 passed, same single pre-existing environment failure as before this change)
