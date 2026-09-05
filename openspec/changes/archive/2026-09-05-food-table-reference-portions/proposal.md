## Why

A vague portion question about a condiment-scale food proposes plate-scale weights: the
screenshot that started this is "cipolla" offered at piccolo ~80g / medio ~120g /
abbondante ~180g, roughly double a real onion portion. The generic 80/120/180g fallback
in `portion_options_for` is the floor every vague food name lands on, because the
model's per-food estimates are extracted only when the user stated a household measure,
and most vague messages just name the food. The bundled food table - the project's
authoritative, deterministic source for everything else about a food - knows nothing
about portions.

## What Changes

- Add three reference-portion columns to the bundled food table
  (`portion_small_g`, `portion_medium_g`, `portion_generous_g`), curated as
  self-authored typical Italian household portions for the rows where a portion question
  plausibly arises; rows without a meaningful portion (water, seasonings) stay null.
- `portion_options_for` becomes a tiered lookup: countable-unit multiples first (they
  already are the deterministic source for countable foods and read better as buttons),
  then the food table's reference portions, then the extraction's own estimates, then
  the generic scale.
- The extraction prompt gate relaxes from "only when a household measure is stated" to
  "whenever the quantity is vague or absent", so the model covers the long tail the
  table does not know.
- The options offered with the question are stored with the draft, so the answer maps
  back to the same grams that were shown (the answer path cannot re-run the table
  lookup).
- Migration and seed backfill for the new columns, as for the macro columns.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `food-logging`: the vague-portion clarification offers food-specific gram options -
  from the bundled table when it knows the food, from the extraction when it doesn't -
  instead of a fixed generic scale, with the generic scale as last resort.

## Impact

- `src/calobot/data/food_data.csv` - three new columns, curated values.
- `src/calobot/persistence/models.py` - three nullable columns on `FoodDataRow`.
- Alembic migration; `seed.py` backfill mirroring the macro backfill.
- `src/calobot/food/quantities.py`, `planner.py`, `ingestion/extractors.py`,
  `persistence/candidates.py` - the tiered lookup and its plumbing.
- `docs/DATA_SOURCES.md` - the portions are self-authored household estimates, not from
  any licensed source (CREA stays out).
