## 1. Aggregation

- [x] 1.1 Add `_previous_period_start(period, current_start_day)` to
      `calobot.reporting.aggregation`, deriving the previous period's start date
      directly from the current period's own start date (design.md - Decisions).
- [x] 1.2 Add `PeriodComparison`, `LoggingConsistencySignal`, `MealTimingSignal`,
      `CalorieDensitySignal` and `PeriodComparisonResult` frozen dataclasses.
- [x] 1.3 Add `MIN_DAYS_FOR_SIGNAL` constant (design.md - Decisions).
- [x] 1.4 Implement `build_period_comparison(session, user_id, period, reference_day,
      tz, goal_kg)`:
  - [x] 1.4.1 Comparison: call `build_food_report`, `build_weight_report`,
        `build_activity_report` once for the current period and once for the previous
        period (its own reference day derived from 1.1); diff calories average,
        weight change, activity minutes.
  - [x] 1.4.2 Logging consistency signal for both periods.
  - [x] 1.4.3 Meal-timing drift signal for both periods.
  - [x] 1.4.4 Calorie-density trend signal for both periods.
- [x] 1.5 Unit tests in `tests/test_reporting.py` (or a new
      `tests/test_period_comparison.py`): adjacent-period boundaries for each of
      day/week/month/year (including a December→January and a leap-year February
      case), a comparison with data in both periods, a comparison with no previous-
      period data, and each signal's insufficient-data path.

## 2. Advice tool

- [x] 2.1 Add `get_period_comparison` `ToolDefinition` to
      `calobot.advice.tools.build_tool_registry`, using `PeriodQuery` as its args
      schema (reuses the existing period/reference_day shape) and wrapping
      `build_period_comparison`.
- [x] 2.2 Shape the handler's returned dict so `no_data`/insufficient-data cases are as
      explicit as every other tool's payload (specs/advice-agent - Absent data is
      reported as absent, not estimated).
- [x] 2.3 Tests in `tests/test_advice_tools.py`: comparison for a user with two
      periods of data, a user with only the current period, and a user whose data
      doesn't clear `MIN_DAYS_FOR_SIGNAL` for any signal.

## 3. Advice agent prompt

- [x] 3.1 Mention `get_period_comparison` in `GATHER_SYSTEM_PROMPT` in
      `calobot.advice.agent`, framed for "sto migliorando?" / "come mi sto
      comportando ultimamente?" style questions, and note that its signals already
      state when there isn't enough data rather than needing the model to hedge.

## 4. Verification

- [x] 4.1 `task check` passes.
- [x] 4.2 Manual review: confirm no new query path skips `deleted_at` filtering, since
      every read goes through `get_entries_in_range`/`get_weight_entries_in_range`,
      which already exclude it.
