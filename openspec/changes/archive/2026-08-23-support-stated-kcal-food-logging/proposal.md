## Why

When a user states a calorie value directly (e.g. "100kcal di melanzane sott'olio"), the extraction schema has no field to capture it, so the LLM has nowhere to put the number except `quantity_grams`. The pipeline then treats "100" as a gram quantity and computes kcal forward from the bundled/estimated energy density (kcal_per_100g), silently discarding the value the user actually stated and confirming a wrong number back to them (e.g. "100g - 25 kcal" instead of "100 kcal").

## What Changes

- Add a `stated_kcal` field to the food extraction schema (`FoodItemExtraction`) and prompt so the LLM can capture an explicitly stated calorie value, distinct from grams/count.
- When `stated_kcal` is present, the stored kcal value SHALL be that stated value directly, not a forward computation from resolved energy density.
- When `stated_kcal` is present, the system SHALL still resolve an energy density (via the existing hybrid resolution: cache → table → LLM) and back-derive an estimated gram quantity (`grams = stated_kcal / kcal_per_100g * 100`) for storage and reporting, so downstream consumers that read `grams` keep working.
- If energy density cannot be resolved, or resolves to zero, the entry SHALL still be stored with the stated kcal and grams SHALL be left as an explicit "unknown" marker rather than a divide-by-zero or a fabricated number.
- The confirmation message SHALL reflect that the calories were stated by the user (rather than a plain "Xg - Y kcal" that implies both were derived), and SHALL indicate grams as approximate when back-derived.

## Capabilities

### Modified Capabilities
- `food-logging`: entries may now originate from a user-stated calorie value rather than a resolved quantity; requirements for entry contents, quantity resolution and confirmation wording change to cover this case.

## Impact

- `src/calobot/ingestion/schemas.py` (`FoodItemExtraction`) — new field.
- `src/calobot/ingestion/extractors.py` (`FOOD_PROMPT`) — prompt guidance for the new field.
- `src/calobot/food/planner.py` (`finalize_item`) — branch to use stated kcal as authoritative and back-derive grams.
- `src/calobot/food/resolver.py` — reused as-is for density resolution; no interface change expected.
- `src/calobot/ingestion/pipeline.py` (`_food_confirmation`) — confirmation wording for stated-kcal entries and unknown-grams entries.
- Any report/export path that assumes `grams` is always a directly stated quantity should tolerate an "unknown" grams marker.
