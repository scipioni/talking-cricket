# Bundled seed data — sources and licensing

This directory ships two datasets inside the application image. Both are chosen and
compiled specifically to avoid the licensing problems of the obvious alternatives
(CREA tables, the Compendium of Physical Activities) — see `design.md` — Calorie
resolution and — Energy model in `openspec/changes/calobot-v1/`.

## `food_data.csv` — energy per 100 g for common foods

**Source:** USDA FoodData Central, *Foundation Foods* / *SR Legacy* CSV export,
downloaded directly from https://fdc.nal.usda.gov/download-datasets (Foundation
Foods release 2026-04-30; SR Legacy's final release, April 2018 — it is not
updated further). **Licence confirmed at the primary source**
(https://fdc.nal.usda.gov/api-guide/): *"USDA FoodData Central data are in the
public domain and they are not copyrighted. They are published under CC0 1.0
Universal."* No permission is required for any use; attribution is requested,
not mandatory. This is why FDC was chosen over CREA (no open licence, plus the EU
*sui generis* database right) and over OpenFoodFacts (ODbL share-alike, better
suited to a runtime barcode lookup than a bundled table).

**How the rows were built:** each row's `source_name_en` and `kcal_per_100g` were
matched against the real FDC data by exact substring search on FDC's systematic
naming (e.g. `"nuts", "walnuts", "english"` → `"Nuts, walnuts, english"`), reading
the `1008` ("Energy", KCAL) nutrient value from `food_nutrient.csv` for the
matched `fdc_id`. Every match was reviewed individually before being applied —
an initial attempt at fuzzy top-1 matching (rapidfuzz `WRatio`) produced silently
wrong pairings (e.g. "Sunflower oil" → "Cauliflower, raw") and was discarded
entirely rather than shipped; see the git history of this file if that attempt's
transcript is ever needed for reference. **135 of 161 rows are verified against
this real download.** The remaining 26 are hand-authored estimates, kept because
they are either genuinely Italian/European specialty items with no equivalent
generic entry in a US-centric database (`Prosciutto crudo`, `Bresaola`,
`Mortadella`, `Stracchino`, `Gorgonzola`, `Pecorino`, `Mascarpone`, `Nutella`,
`Cappuccino`), or common items a quick search did not confidently resolve
(`Pasta dry/cooked`, `Breadsticks`, `Rusks`, `Couscous cooked`, `Polenta cooked`,
`Pizza dough`, `Beans borlotti cooked`, `Beef ground raw`, `Pork sausage`,
`Bacon`, `Sea bream raw`, `Milk semi skimmed`, `Yogurt greek`, `Salami`). These
26 are unverified estimates, not table-grade data — resolving them further (or
letting them fall through to LLM estimation at runtime, which is the documented
fallback for exactly this case) is a fair next step, not a defect to hide.

## `food_data.csv` — `protein_per_100g`, `fat_per_100g`, `carbs_per_100g`, `fiber_per_100g`

Added by `add-macro-nutrient-tracking` (see `openspec/changes/`). Unlike `kcal_per_100g`,
these four columns were **not** individually matched against a downloaded FDC export row by
row — no such download was available in the environment this change was authored in. They
are standard, widely-published nutrition figures for each named food, filled in from general
nutrition knowledge as a documented best-effort placeholder for every one of the 161 rows
(not only the 26 rows already called out above as hand-authored estimates for
`kcal_per_100g`). They are **not held to the same per-row FDC verification** the energy
column has.

Anyone tightening this later should treat it the same way the original `kcal_per_100g` fuzzy
top-1 attempt was treated: re-derive these four columns from an actual FDC (or other CC0/
public-domain) download, nutrient IDs 203 (protein), 204 (fat), 205 (carbohydrate) and 291
(fiber), reviewing each match individually rather than trusting an automated join — same
rationale as the walnut/cauliflower mismatch noted below for energy.

## `food_data.csv` — `aliases_it` column (the Italian alias index)

Generated to let fuzzy retrieval work against Italian text even though the source
rows are in English — the language model then *disambiguates* among retrieved
candidates rather than needing to *translate* (design.md — "The LLM erases USDA's one
drawback"). For this build these aliases were written by hand alongside each row
rather than produced by a live seed-time model call (no LLM endpoint was reachable
in this environment); functionally this is the same artifact the design calls for —
a committed, reviewable, hand-correctable index — just authored directly instead of
generated-then-corrected. `scripts/generate_aliases.py` implements the LLM-assisted
generation path for extending the table later.

## `met_data.csv` — metabolic equivalents for activities

An original compilation of ~70 activities relevant to an Italian-speaking user of a
weight-tracking bot, in Italian, with intensity variants where the MET value
materially depends on pace or effort. Deliberately **not** copied from the
Compendium of Physical Activities: a MET value is a physiological fact and is not
copyrightable, but the Compendium's selection and arrangement of ~800 activities is
its authors' work, and copying that structure would carry the same licensing risk as
copying CREA's table structure. Values here are the widely documented physiological
estimates found across public fitness and exercise-physiology references for each
activity; the selection, wording and Italian phrasing are original to this project.

## Summary of redistribution obligations

| File | Obligation |
|---|---|
| `food_data.csv` (energy values) | None — public domain facts / USDA-style public domain source |
| `food_data.csv` (macro values) | None — physiological facts, not a copyrightable selection; not yet individually FDC-verified (see above) |
| `food_data.csv` (`aliases_it`) | None — original compilation |
| `met_data.csv` | None — original compilation |

Neither file bundles any OpenFoodFacts- or CREA-derived data, so ODbL share-alike and
CREA's lack-of-licence do not apply to anything shipped in this image.
