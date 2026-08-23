## Context

Food extraction (`FoodItemExtraction` in `src/calobot/ingestion/schemas.py`) currently has no field for a calorie value the user states directly, so "100kcal di melanzane sott'olio" is misread into `quantity_grams=100`. `finalize_item` (`src/calobot/food/planner.py`) then always computes `kcal = kcal_per_100g * grams / 100`. `FoodEntry.grams`, `.kcal`, `.kcal_per_100g` (`src/calobot/persistence/models.py`) are all non-nullable `Float` columns. `_food_confirmation` (`src/calobot/ingestion/pipeline.py`) always renders `"{grams}g - {kcal} kcal"`. `dietician.py:96` sums `e.grams` across entries for reporting. See proposal.md for the full motivation.

## Goals / Non-Goals

**Goals:**
- Capture a directly stated calorie value at extraction time, distinct from grams/count.
- Make stated kcal authoritative for the entry's `kcal`, with grams back-derived from density when resolvable.
- Represent "grams genuinely unknown" without a fabricated number or a divide-by-zero.

**Non-Goals:**
- Changing how quantity resolution works when no calorie value is stated (existing grams/count/household-measure paths are untouched).
- Letting a user state both a quantity and a conflicting calorie value and having the system reconcile them beyond "stated kcal wins" — that combination is out of scope; if both are present, stated kcal is authoritative and grams is back-derived exactly as when only kcal was given.

## Decisions

**New field `stated_kcal: float | None` on `FoodItemExtraction`.** Kept as its own field (not reusing `quantity_grams`) so the LLM has an explicit slot for "this number is calories," matching the project's convention of small flat fields per intent rather than overloading an existing one. Range-limited (`ge=0, le=5000`) like the other quantity fields.

**`finalize_item` branches on `stated_kcal` before touching quantity resolution.** When present: `kcal = item.stated_kcal` directly; energy density is still resolved via `resolve_food_energy` (unchanged hybrid cache → table → LLM resolution, needed anyway for provenance and for back-deriving grams) and `grams = stated_kcal / kcal_per_100g * 100` when `kcal_per_100g > 0`, else `grams = None`. This keeps `resolve_food_energy` untouched — it already returns `kcal_per_100g` and `provenance`, both needed regardless of which direction the arithmetic runs.

**`FoodEntry.grams` becomes nullable.** Alternatives considered: a sentinel value (e.g. `-1` or `0`) to avoid a migration — rejected because it is exactly the kind of implicit, easily-forgotten convention the codebase avoids elsewhere (soft-delete uses a real nullable `deleted_at`, not a sentinel). A new Alembic migration (`task migration -- "..."`) makes `grams` nullable; `kcal` and `kcal_per_100g` stay non-nullable since both are always known (stated directly, or resolved density) whenever an entry is stored.

**`check_item`/`resolve_quantity` clarification path is bypassed when `stated_kcal` is present**, even if grams/count are also unresolved — the entry has enough information to store (kcal) without needing a portion-size answer. This is a small early-return added in `check_item` before it calls `resolve_quantity`.

**Confirmation message.** When `kcal` came from `stated_kcal`, `_food_confirmation` renders calories first and marks grams as approximate when present (e.g. `"Registrato: melanzane sott'olio - 100 kcal (~400g stimati)"`) or omits grams entirely when unresolved (e.g. `"Registrato: melanzane sott'olio - 100 kcal (grammi non stimabili)"`). This requires `_food_confirmation` to know whether the entry's kcal was stated rather than derived — the simplest carrier is a new boolean on `FinalizedFood` (`kcal_is_stated: bool`), mirroring the existing `is_estimate` / `quantity_is_estimated_from_count` flags rather than inferring it after the fact from the entry alone.

**`dietician.py:96`'s `sum(e.grams for e in entries)`** is updated to skip entries with `grams is None` (`sum(e.grams for e in entries if e.grams is not None)`), since a handful of stated-kcal entries with unknown grams should not crash or silently coerce to zero.

## Risks / Trade-offs

- **Ambiguous input where "100" could plausibly be grams or kcal** (e.g. a message with a bare number and no unit word) → mitigated by the extraction prompt only setting `stated_kcal` when a calorie unit word ("kcal", "calorie") is explicit, exactly as `quantity_grams` is already gated on an explicit gram/ml unit.
- **Migration risk**: making a previously non-nullable column nullable is a low-risk, backward-compatible schema change (existing rows are unaffected; only new stated-kcal entries will have `NULL` grams) — no backfill needed.
- **Downstream code reading `grams` unconditionally**: only one other call site was found (`dietician.py:96`); any future report/export code must be written to tolerate `None` grams from here on.

## Migration Plan

1. Add the Alembic migration for `grams` nullability (`task migration -- "make food_entries.grams nullable"`).
2. Ship schema/prompt/planner/confirmation changes together (they are not independently useful).
3. No rollback complexity beyond a standard migration downgrade; no data backfill is required since existing entries already have non-null `grams`.
