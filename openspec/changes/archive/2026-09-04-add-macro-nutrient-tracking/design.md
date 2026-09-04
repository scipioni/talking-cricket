## Context

Energy resolution today is a single hybrid path: `resolve_food_energy` in
`src/calobot/food/resolver.py` checks `ResolutionCache` (keyed on a normalized
description), then `retrieve_food_candidates` over the bundled `FoodDataRow` table
(`src/calobot/data/food_data.csv`, currently `source_name_en, kcal_per_100g, aliases_it`),
then an LLM estimate (`EstimateResult`). Whichever path wins, the result is written back
into `ResolutionCache` under a trust order (`etichetta` > `off` > `tabella` > `llm`), and
`FoodEntry` stores the resolved `kcal_per_100g` and the entry's absolute `kcal`. Grams are
either the user's stated/resolved quantity or, when only kcal was stated, back-derived from
kcal and `kcal_per_100g` (nullable when that derivation is not possible). See
proposal.md - Why for what's missing today: nothing above stores protein, fat, carbohydrate
or fiber.

## Goals / Non-Goals

**Goals:**
- Resolve and store macro grams (protein, fat, carbohydrate, fiber) using exactly the same
  cache → table → LLM path and trust ordering as kcal, so behavior stays predictable and
  consistent with the food-logging spec's existing resolution-cache guarantees.
- Add one report topic (`macros`) and one chart type, following the shape of the existing
  `food`/`weight`/`activity` topics and `render_calorie_chart`/`render_weight_chart`.
- Provide a one-off way to backfill macros for `FoodEntry` rows logged before this change,
  so a macro report over a period spanning old and new entries isn't missing data purely
  because of when a food happened to be logged.

**Non-Goals:**
- No micronutrients (vitamins, minerals, sodium, sugar breakdown). Only the four macros the
  user asked about.
- No macro-based budget or goal (e.g. a protein target) — this change reports what was
  consumed, it does not evaluate it against a target, mirroring how the activity report is
  purely informational.
- No automatic/scheduled backfill — it's an explicitly-run, one-off maintenance script (see
  Decisions), not a background job that keeps re-resolving historical entries.

## Decisions

**One combined resolution result, not four separate lookups.** `ResolvedFood` gains four
new optional-but-usually-present fields (`protein_per_100g`, `fat_per_100g`,
`carbs_per_100g`, `fiber_per_100g`) instead of resolving each macro independently. The table
lookup and the LLM estimate call both already produce "nutritional facts for this food" in
one shot; splitting macros into separate calls would violate the small-flat-schema
convention less than it would just be wasteful and could disagree with each other (different
LLM call, different guess) for the same food. `EstimateResult` and `FoodCandidate` /
`FoodDataRow` gain the same four fields; `RowSelection` is unchanged (it only picks an id).

**Nullable at every layer, no zero-substitution.** A macro that can't be resolved (e.g. an
old estimate, or a table row that lacks it) is stored as `None`, never `0` — the same
reasoning as the existing nullable `FoodEntry.grams`. A zero would be indistinguishable from
"this food genuinely has no fiber" and would corrupt a distribution chart's totals silently.
Report aggregation (total/average per macro) must therefore skip nulls per macro
independently rather than per entry, since one food might resolve fat but not fiber.

**`food_data.csv` gains four macro columns.** The original `kcal_per_100g` column was built
by hand-matching rows against an actual downloaded USDA FDC export that is not available in
this environment. Re-deriving that download was out of reach for this change (confirmed with
the user), so the four macro columns were filled for all 161 rows from general nutrition
knowledge as a documented best-effort placeholder, explicitly *not* held to the same per-row
FDC-verification bar as `kcal_per_100g` — `DATA_SOURCES.md` is amended to say so plainly and
to point at nutrient IDs 203/204/205/291 as what a future FDC-backed pass should re-derive
against. These are physiological facts, not a copyrightable selection, so this doesn't change
the file's licensing story.

**`ResolutionCache` and the Alembic migration add four nullable float columns to both
`resolution_cache` and `food_entries`.** The migration itself does no data backfill — it only
adds columns, matching the project's "never `create_all`, always a migration" rule and
keeping schema change and data change separately reviewable/rollback-able.

**Backfill is a standalone script (`scripts/backfill_macros.py`), following the existing
`scripts/migrate_user_id.py` precedent, not a migration data step or a background job.** It:
1. Selects distinct normalized descriptions across non-deleted `FoodEntry` rows whose macro
   columns are all null.
2. Runs each through the same `resolve_food_energy`-style path, but only requests/stores the
   macro fields — it does not touch `kcal`, `kcal_per_100g` or `grams`, so it cannot alter a
   user's historical calorie figures, only add previously-missing macro data alongside them.
3. Writes the result into `ResolutionCache` exactly as a live resolution would (same trust
   ordering), then updates every matching `FoodEntry` row's macro grams by scaling the
   resolved per-100g values by that entry's already-stored `grams` (entries with null
   `grams` are left with null macros, same as a live resolution would leave them).
4. Is idempotent and safe to re-run: rows that already have non-null macros, or whose `grams`
   is null, are skipped.
This is a one-off maintenance script rather than a migration step because it makes LLM calls
(non-deterministic, rate-limited, potentially costly across a large history) — the kind of
operation Alembic migrations in this project are not used for.

**Report topic and chart follow the existing per-topic pattern, not a new abstraction.**
`ReportExtraction.topic` becomes `Literal["food", "weight", "activity", "macros", "all"]`.
`_handle_report` in `pipeline.py` gets one new `if extraction.topic == "macros":` branch,
symmetric with the existing `food`/`weight`/`activity` branches — it is deliberately not
folded into `"all"` (per the reporting spec delta, an unscoped report doesn't grow a fourth
section) so unscoped-report behavior is untouched. `render_macro_chart` in
`reporting/charts.py` is a new function alongside `render_calorie_chart`, a stacked bar
chart (one call to a plotting stack already in use, no new charting dependency).

**Disclaimers are edited, not deleted wholesale.** `telegram/handlers.py`,
`reporting/dietician.py` and `advice/agent.py` currently state macros aren't tracked in a
few different framings (a hard capability disclaimer vs. dietary advice hedging). Each call
site is updated in place to reflect that macro grams now exist, rather than assuming a single
shared string can be deleted everywhere.

## Risks / Trade-offs

- **LLM estimate quality for macros is unverified** → mitigate by using the same trust
  ordering and cache-overwrite rules that already govern kcal estimates: a table match
  (`tabella`) still outranks an LLM guess (`llm`), and a later higher-trust resolution (e.g.
  a scanned label) still overwrites a lower-trust one, macros included.
- **All 161 rows' macro values are general-knowledge best-effort figures, not individually
  FDC-verified like `kcal_per_100g`** → documented plainly in `DATA_SOURCES.md` as a known
  gap with the specific nutrient IDs (203/204/205/291) a future pass should re-derive
  against; the resolution cache's trust ordering means a later `tabella`→FDC-verified
  re-import would need a mechanism to override existing `tabella`-provenance cache entries,
  which is out of scope here but not blocked by anything in this design.
- **A stacked bar chart with 4 series is visually busier than the existing single-series
  calorie chart** → use one fixed, distinguishable color per macro (not derived from
  arbitrary data) and keep the legend static, so the chart reads consistently report to
  report.
- **Backfill cost/time scales with the number of distinct historical food descriptions
  across all users, and makes real LLM calls** → run it as an explicit, operator-triggered
  script (not on deploy, not on first request), keyed to distinct normalized descriptions
  (not per-entry) so cost matches vocabulary size, and made idempotent so it can be safely
  interrupted and re-run.

## Migration Plan

1. Alembic revision adding the four nullable columns to `food_entries` and
   `resolution_cache` (`task migration -- "add macro nutrient columns"`).
2. Extend `food_data.csv` with the four columns from the same FDC release, and
   `DATA_SOURCES.md` with the additional nutrient IDs.
3. Land resolver/schema/candidate changes together (they change in lockstep — a
   `ResolvedFood` with new fields is meaningless without a `FoodDataRow`/`EstimateResult`
   that can populate them).
4. Land the report topic, prompt, dispatch branch and chart together.
5. Write and run `scripts/backfill_macros.py` against production data once the above is
   deployed, so historical entries stop reading as macro-null.
6. Update the three disclaimer call sites last, once macros are actually being stored,
   reported, and backfilled, so the copy change reflects shipped behavior.

No rollback complexity beyond a standard Alembic downgrade: the new columns are additive and
nullable, so downgrading drops them without touching existing kcal-based behavior.
