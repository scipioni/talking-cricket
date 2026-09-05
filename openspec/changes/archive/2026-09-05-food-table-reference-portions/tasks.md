## 1. Data and schema

- [x] 1.1 Add `portion_small_g,portion_medium_g,portion_generous_g` to `src/calobot/data/food_data.csv` with curated self-authored values (null where no portion question makes sense); verify the CSV parses and every triple is ascending
- [x] 1.2 Add the three nullable columns to `FoodDataRow` and generate an Alembic migration with `task migration -- "food table reference portions"`; verify `task typecheck` adds no errors
- [x] 1.3 Extend `seed_food_data` to backfill the portion columns for existing rows, mirroring the macro backfill; verify with a unit test seeding twice

## 2. Tiered lookup

- [x] 2.1 Carry the portion columns through `FoodCandidate` and add a `table_portions_for(session, description)` lookup returning the first fully-populated triple; verify with a unit test on a fuzzy match
- [x] 2.2 Make `portion_options_for` tiered (unit multiples → table triple → extraction estimates → generic) with an optional `table_portions` argument; verify with unit tests over all four tiers
- [x] 2.3 In `planner.check_item`, look up the table portions, and store the displayed option map on the draft item; in `apply_answer`, map the tapped label against that stored map first; verify with unit tests that the shown label resolves to the shown grams

## 3. Extraction fallback

- [x] 3.1 Relax the extraction prompt gate for `portion_small_g/medium_g/generous_g` from "only with a stated household measure" to "whenever the quantity is vague or absent"; verify `task typecheck`

## 4. Verification

- [x] 4.1 Add an e2e test: a vague "ho mangiato cipolla" asks with the curated onion scale (~40/60/100g), and tapping piccolo stores ~40g; plus a seed-backfill assertion for the new columns
- [x] 4.2 Run `task check` (expect only the pre-existing lint/type failures) and `openspec validate --changes`; update `docs/DATA_SOURCES.md` with the self-authored portion values note
