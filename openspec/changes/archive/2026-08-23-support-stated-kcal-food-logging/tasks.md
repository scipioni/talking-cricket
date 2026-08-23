## 1. Schema and extraction

- [x] 1.1 Add `stated_kcal: float | None` to `FoodItemExtraction` in `src/calobot/ingestion/schemas.py` and verify existing extraction tests still pass unchanged
- [x] 1.2 Update `FOOD_PROMPT` in `src/calobot/ingestion/extractors.py` to instruct the model to set `stated_kcal` only when a calorie unit ("kcal", "calorie") is explicit, and to leave `quantity_grams`/`quantity_count` unset in that case; add/adjust an extraction test for "100kcal di melanzane sott'olio" asserting `stated_kcal == 100` and `quantity_grams is None`
- [x] 1.3 Propagate `stated_kcal` through `build_items`/`_as_extraction_fields` in `src/calobot/food/planner.py` so it survives into the draft item dict and back into `FoodItemExtraction`

## 2. Persistence

- [x] 2.1 Run `task migration -- "make food_entries.grams nullable"`, edit the generated revision to alter `food_entries.grams` to nullable, and update `FoodEntry.grams` to `Mapped[float | None]` with `nullable=True` in `src/calobot/persistence/models.py`
- [x] 2.2 Verify the migration applies cleanly against the existing schema (`task test` covers migration application via the test DB setup) and that no existing non-null `grams` rows are affected

## 3. Planner logic

- [x] 3.1 In `check_item` (`src/calobot/food/planner.py`), early-return `None` (no clarification needed) when `item.get("stated_kcal")` is present, bypassing `resolve_quantity`'s portion-size clarification
- [x] 3.2 Add `kcal_is_stated: bool` to `FinalizedFood`
- [x] 3.3 In `finalize_item`, when `stated_kcal` is present: set `entry.kcal = stated_kcal` directly, still call `resolve_food_energy` for `kcal_per_100g`/provenance, and set `entry.grams = stated_kcal / kcal_per_100g * 100` when `kcal_per_100g > 0` else `None`; set `kcal_is_stated=True` on the returned `FinalizedFood`
- [x] 3.4 Add unit tests for `finalize_item` covering: stated kcal with resolvable density (grams back-derived correctly), stated kcal with zero/unresolvable density (grams is `None`, no exception), and the existing grams-first path unaffected (`kcal_is_stated=False`)

## 4. Confirmation message

- [x] 4.1 Update `_food_confirmation` in `src/calobot/ingestion/pipeline.py` to render a stated-kcal entry as calories-first, showing back-derived grams as approximate (e.g. `"~400g stimati"`) when `entry.grams is not None`, or omitting grams (e.g. `"grammi non stimabili"`) when `None`
- [x] 4.2 Add/adjust a pipeline test asserting the confirmation text for "100kcal di melanzane sott'olio" reports 100 kcal (not a recomputed value) and does not crash when grams is `None`

## 5. Downstream consumers

- [x] 5.1 Update `src/calobot/reporting/dietician.py:96` to `sum(e.grams for e in entries if e.grams is not None)` and verify the dietician report test suite still passes
- [x] 5.2 Grep the codebase for other unconditional `.grams` reads on `FoodEntry` introduced since design.md was written, and guard any found against `None`

## 6. Spec sync

- [x] 6.1 After implementation and tests pass, sync the `food-logging` delta spec into `openspec/specs/food-logging/spec.md` (`task check` green beforehand)
