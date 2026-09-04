## 1. Schema

- [x] 1.1 Add `AdviceSurface` (`dietician_review`, `daily_advice`, `advice_agent`),
      `AdviceTopic` (`meal_timing`, `logging_consistency`), and `AdviceOutcome`
      (`undetermined`, `followed`, `not_followed`) enums, and an `AdviceRecord` model
      (`advice_records` table) to `calobot.persistence.models`, following the
      `deleted_at`/`created_at` conventions `FoodEntry` already uses.
- [x] 1.2 `task migration -- "add advice_records table"`.
- [x] 1.3 Add `AdviceRecord` to the loop in `hard_delete_user`
      (`persistence/repository.py`).
- [x] 1.4 Repository accessors: `create_advice_record`, `get_recent_advice_records`
      (filters `deleted_at`, orders newest-first), `get_latest_advice_by_category`
      (for suppression), `get_undetermined_advice_by_topic` (for outcome resolution),
      `set_advice_outcome`.

## 2. Recording and classification

- [x] 2.1 New module `calobot.advice.memory`:
  - [x] 2.1.1 `classify_topic(text: str) -> AdviceTopic | None` — deterministic
        keyword classifier (design.md - Decisions).
  - [x] 2.1.2 `record_advice(session, user, surface, category, content, situation) ->
        AdviceRecord` — classifies topic, writes the row.
  - [x] 2.1.3 `resolve_pending_outcomes(session, user, tz) -> None` — walks
        undetermined, topic-tagged, sufficiently-old records; computes the relevant
        signal before/after via `calobot.reporting.aggregation`; persists a
        determined outcome where the after-window clears `MIN_DAYS_FOR_SIGNAL`.
  - [x] 2.1.4 `previous_unresolved_tip(session, user, category) -> str | None` — the
        suppression lookup.

## 3. Wiring the three emission sites

- [x] 3.1 `calobot.reporting.dietician.build_dietitian_review` and
      `build_daily_advice` gain an optional `avoid_repeating: str | None` param,
      appended to their system prompts as an explicit "don't repeat this verbatim"
      instruction when set.
- [x] 3.2 `ingestion/pipeline.py`'s two call sites: look up
      `previous_unresolved_tip` before calling the builder, pass it through, and call
      `record_advice` after a review/advice is produced (surface `dietician_review`
      with category `dietician_tip_{period}`, surface `daily_advice` with category
      `daily_rest_of_day`).
- [x] 3.3 `advice/agent.py`'s `answer()`: once `derived is not None` and the final
      `reply` has passed the existing consistency/claim checks, call `record_advice`
      with surface `advice_agent`, category `meal_suggestion`, situation
      `f"suggestion_mode={derived.mode}"`.

## 4. Read-only tool

- [x] 4.1 Add `get_advice_history` to `advice/tools.py`'s registry: calls
      `resolve_pending_outcomes` then returns recent records (surface, category,
      content, created_at, outcome).
- [x] 4.2 Mention the tool in `GATHER_SYSTEM_PROMPT` for questions like "il consiglio
      di ieri ha funzionato?".

## 5. No-retention and /cancellami

- [x] 5.1 Confirm (with a test, not just inspection) that `record_advice` writes made
      during no-retention mode are discarded by `NonRetentiveAsyncSession.commit`
      exactly like every other write — no new per-call check should be needed given
      design.md - Decisions, but verify rather than assume.
- [x] 5.2 Confirm `/cancellami` removes advice records (covered by 1.3, verified by a
      test).

## 6. Tests

- [x] 6.1 `classify_topic` on representative tip text for each topic and for
      no-match text.
- [x] 6.2 `record_advice` from each of the three surfaces.
- [x] 6.3 `resolve_pending_outcomes`: followed, not-followed, and not-enough-data-yet
      for both topics.
- [x] 6.4 `previous_unresolved_tip` returns the tip only when unresolved and within
      the same category, not after it's resolved.
- [x] 6.5 `get_advice_history` tool test.
- [x] 6.6 No-retention mode: advice recorded during `/memory_off` does not survive.
- [x] 6.7 `/cancellami` removes advice records.

## 7. Verification

- [x] 7.1 `task check` passes (diffed against the pre-existing baseline established
      when `advice-longitudinal-signals` landed).
