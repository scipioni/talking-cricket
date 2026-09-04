## 1. Data model and migration

- [x] 1.1 Add nullable `protein_g`, `fat_g`, `carbs_g`, `fiber_g` float columns to `FoodEntry`
      in `src/calobot/persistence/models.py`, mirroring the nullable `grams` precedent
- [x] 1.2 Add nullable `protein_per_100g`, `fat_per_100g`, `carbs_per_100g`,
      `fiber_per_100g` float columns to `ResolutionCache` and to `FoodDataRow`
- [x] 1.3 Generate the Alembic revision with `task migration -- "add macro nutrient
      columns"` and verify it upgrades and downgrades cleanly against a scratch SQLite db

## 2. Bundled data

- [x] 2.1 Extend `src/calobot/data/food_data.csv` with `protein_per_100g`, `fat_per_100g`,
      `carbs_per_100g`, `fiber_per_100g` columns for all 161 rows. The original FDC download
      used to hand-match `kcal_per_100g` was not available in this environment; per explicit
      user decision, values were filled from general nutrition knowledge as a best-effort
      placeholder for every row rather than left blank or partially web-verified. Verified
      the CSV still parses (161 data rows) and every row's existing `kcal_per_100g`/
      `aliases_it`/`source_name_en` values are byte-for-byte unchanged.
- [x] 2.2 Updated `src/calobot/data/DATA_SOURCES.md`: documented that the four macro columns
      are a best-effort placeholder, not individually FDC-verified like `kcal_per_100g`, and
      named nutrient IDs 203/204/205/291 for a future verified re-derivation; added a
      redistribution-obligations row for the macro values (none — physiological facts).

## 3. Resolution path

- [x] 3.1 Add the four macro fields to `FoodCandidate` (`persistence/candidates.py`) and
      populate them in `retrieve_food_candidates`. Also updated `persistence/seed.py`
      (`seed_food_data`) to read the new CSV columns into `FoodDataRow` - required plumbing
      not called out explicitly in this task but necessary for the CSV values to reach the
      resolution path at all.
- [x] 3.2 Add the four macro fields to `EstimateResult` and update the LLM estimate prompt
      in `food/resolver.py` to request them alongside `kcal_per_100g`
- [x] 3.3 Add the four macro fields to `ResolvedFood` and thread them through
      `resolve_food_energy`: from the matched table row when the table path is taken, from
      the LLM estimate when that path is taken, defaulting to `None` when a specific macro is
      absent from either source
- [x] 3.4 Extend `write_resolution` and the `ResolutionCache` read/write path to carry the
      four macro fields under the existing trust-ordering rule
- [x] 3.5 Wire the resolved macros into `FoodEntry` creation - the actual construction site
      is `food/planner.py::finalize_item` (tasks.md said `ingestion/pipeline.py`; corrected
      here), scaling per-100g macro values by the entry's resolved grams the same way kcal is
      scaled, `None` when grams is unresolved. Also fixed two correction paths that would
      otherwise have gone stale against the newly-consistent macros: quantity-only correction
      (`corrections/service.py::amend_food_quantity`, rescales existing macro grams by the
      grams ratio) and description correction (`ingestion/pipeline.py`, re-resolves macros
      alongside kcal) - both needed so a corrected entry's macros stay consistent with its
      corrected quantity/description, per the spec's "same portion, same macros" requirement.

## 4. Report topic and extraction

- [x] 4.1 Add `"macros"` to the `ReportExtraction.topic` `Literal` in
      `ingestion/schemas.py`
- [x] 4.2 Update `REPORT_PROMPT` in `ingestion/extractors.py` to describe when a request is
      about macro distribution versus `food`

## 5. Macro report and chart

- [x] 5.1 Added `build_macro_report` and `build_daily_macro_breakdown` to
      `reporting/aggregation.py` (alongside `build_food_report`/`build_daily_kcal_breakdown`):
      total and daily-average grams per macro over the period, skipping null values per macro
      independently, with the same days-with-no-data identification as the calorie report.
      Verified with `test_macro_report_over_a_week_sends_a_chart` (integration) using an
      entry with resolved macros.
- [x] 5.2 Added a `topic == "macros"` branch in `_handle_report` (`ingestion/pipeline.py`),
      symmetric with the `food`/`weight`/`activity` branches, including the
      no-data-for-topic response. Verified with `test_macro_report_with_no_data` (empty
      period) and `test_macro_report_over_a_week_sends_a_chart` (populated period).
- [x] 5.3 Added `render_macro_chart` to `reporting/charts.py`: a stacked bar chart, one bar
      per day, fixed per-macro color (`MACRO_COLORS`) and Italian legend/labels, week+ only.
- [x] 5.4 Wired `render_macro_chart` into the `macros` branch for `period != "day"`, mirroring
      the existing calorie-chart period gate; day-period macro reports return text only
      (same `if period != "day"` guard as the food/weight branches).

## 6. Backfill historical entries

- [x] 6.1 Wrote `scripts/backfill_macros.py`: selects non-deleted `FoodEntry` rows with known
      `grams` and all-null macros, groups by exact stored `description` (the same string
      originally passed to `resolve_food_energy`, so it hits the same cache key), resolves
      macros once per distinct description via `resolve_food_energy` (which itself writes
      into `ResolutionCache` under the existing trust ordering), then scales each entry's
      macro grams from its own stored `grams` - `kcal`/`kcal_per_100g`/`grams` are never
      assigned. Core logic lives in a testable `backfill_macros(session, gateway)` function;
      `main()` is a thin CLI wrapper with `--dry-run`. Verified idempotent in
      `tests/test_backfill_macros.py::test_backfill_is_idempotent` - the second run stages no
      LLM response, so if it attempted another resolution the scripted gateway would raise.
- [x] 6.2 Verified in `tests/test_backfill_macros.py::test_backfill_resolves_macros_and_leaves_kcal_and_grams_unchanged`
      that `kcal`, `kcal_per_100g` and `grams` are byte-for-byte unchanged after backfill, and
      in `test_backfill_skips_entries_with_unresolved_grams` that a null-`grams` entry is left
      with null macros and untouched `kcal`.
- [x] 6.3 The project has no separate ops/runbook doc - `scripts/migrate_user_id.py`, the
      existing one-off maintenance script precedent, documents its own usage in its module
      docstring with no separate runbook entry either. Followed the same convention:
      `scripts/backfill_macros.py`'s docstring documents usage, behavior and safety
      (idempotent, never touches kcal/grams); `design.md`'s Migration Plan step 5 already
      names it as the post-deploy step to run.

## 7. Retire the "macros not tracked" disclaimers

- [x] 7.1 Updated `HELP_TEXT` in `telegram/handlers.py`: added a macro-report example, and
      changed the disclaimer line to state calories+macros are tracked, sodium/sugar are not
      (previously claimed macros weren't tracked at all). This required a spec fix not
      anticipated by this task: `specs/help-and-welcome`'s "The help text states what the bot
      does not track" requirement hard-coded macronutrients as the not-tracked example - added
      a MODIFIED delta (`specs/help-and-welcome/spec.md`) and updated the corresponding test
      (`test_welcome_message.py::test_help_text_states_that_macronutrients_are_tracked_but_sodium_and_sugar_are_not`,
      renamed from the old assertion).
- [x] 7.2 Updated `reporting/dietician.py` and `advice/agent.py`. This surfaced a real scope
      question, put to the user: `advice-agent` and `dietician-reviews` don't just disclaim
      macros, they justify a "never state a gram amount" behavior by claiming macros aren't
      tracked - which is now false. Decided (explicit user choice): keep the qualitative-only,
      no-gram-amount behavior exactly as is (these prompts still don't feed macro numbers into
      their LLM calls), but correct the justification to "deliberate conversational-tone
      choice" rather than "data doesn't exist". Added MODIFIED deltas for
      `specs/advice-agent/spec.md` (including a new scenario for a stray conversational macro
      question, redirected to the macro report) and `specs/dietician-reviews/spec.md`.
      `advice/agent.py`'s tool-use guidance was also corrected: it still has no macro
      retrieval tool, so it must still refuse to estimate macros, but no longer claims the bot
      doesn't track them - it now points the user at the macro report instead.
- [x] 7.3 `task check` equivalent run: `uv run pytest` (503 passed after the fixes above),
      `uv run ruff check src/ tests/ scripts/` (zero new findings - the pre-existing 65
      findings in untouched files are unrelated to this change), `uv run mypy src/` (the same
      5 pre-existing errors as on `main`, confirmed via `git stash`, none introduced by this
      change).
