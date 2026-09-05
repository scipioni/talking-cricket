## Context

`portion_options_for(item)` today: extraction-supplied estimates (gated on a stated
household measure) → unit-weight multiples → generic 80/120/180g. The question is built
in `planner.check_item` (async, has the session); the answer is applied in
`planner.apply_answer` (sync, no session) by mapping the tapped label back to grams.

## Goals / Non-Goals

**Goals:** food-specific options from the bundled table for the common vague case;
model estimates as a fallback for the long tail; generic scale only as last resort.
**Non-Goals:** no change to what is stored (options remain suggestions the user can
override with free text); no assumed portion without asking; no re-licensing of portion
data (CREA stays out - values are self-authored estimates documented in
DATA_SOURCES.md).

## Decisions

### Reference portions live in the bundled CSV, not in code

A `portion_small_g/medium_g/generous_g` triple per `food_data.csv` row, seeded into
`food_data_rows` like the macros, backfilled for existing rows by the same loop. The
table is already the project's authoritative, deterministic, offline food source; a
dict in Python would be a second table to keep in step. Rows without a plausible
portion question (water, seasonings, vinegars) stay null and fall through the tiers.

### Tier order: unit multiples → table → extraction → generic

The proposal's "table first" is about *table before model*. Countable-unit multiples
stay ahead of the table because they are the deterministic countable-food source
already, and "1 uovo (~55g) / 2 uova / 3 uova" reads better than piccolo/medio/abbondante
for an egg. Everything non-countable asks with the table's piccolo/medio/abbondante
when the table knows the food; the extraction's estimates - now also produced for bare
food names, not only stated household measures - cover what the table does not know;
the generic scale remains the floor.

### The offered options travel with the draft

`apply_answer` maps the tapped label to grams and cannot re-run the table lookup (sync,
no session) - and re-running it could even return different candidates. So
`check_item` stores the option map it displayed on the draft item, and `apply_answer`
maps against that stored map first. Free-text answers keep their existing parse path.

### Curated coverage, not forced coverage

Portions are filled for rows where a "quanto pesava la porzione" question plausibly
arises (~150 of 161 rows; water, salt, pepper, dried herbs and the like stay null).
A null is invisible: that row simply falls through to the next tier.

## Risks / Trade-offs

- [Curated values are estimates and may be argued with] → they are displayed as
  tappable suggestions (~Ng), never assumed; the user can always type grams. The
  values are documented as self-authored in DATA_SOURCES.md, keeping the CC0 stance.
- [Two sources of truth for a portion (table vs extraction estimates)] → the tier
  order makes the table win deterministically where it knows the food; the extraction
  only speaks for the long tail.
- [Fuzzy retrieval picks the wrong row for the portions] → retrieval is the same
  `retrieve_food_candidates` the calorie path uses and only the first candidate with a
  full portion triple is used; a wrong match costs a wrong suggestion label, which the
  user overrules by typing.
