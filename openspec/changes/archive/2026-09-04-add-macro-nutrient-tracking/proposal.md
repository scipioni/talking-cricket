## Why

A user asked for "il grafico della distribuzione di proteine, grassi, carboidrati e fibre
delle ultime 2 settimane" and the bot silently rendered a daily-calories chart instead,
because Calobot resolves and stores only kilocalories for a food entry — it has no concept
of grams of protein, fat, carbohydrate or fiber anywhere in the pipeline. The classifier's
`ReportExtraction.topic` enum has no macro value, so a macro request falls back to the
`food` topic and gets whatever that topic renders, with nothing telling the user their
actual question went unanswered. Users logging food conversationally are a natural fit for
also wanting macro-level feedback, and the bot already tells them explicitly that it
doesn't track macros (`telegram/handlers.py` disclaimer) — this change removes that gap
rather than continuing to work around it.

## What Changes

- Resolve protein, fat, carbohydrate and fiber grams per 100g alongside kcal per 100g,
  through the same hybrid cache → bundled table → LLM path `resolve_food_energy` already
  uses, and derive absolute grams for the entry from its resolved portion the same way
  kcal is derived today.
- Extend the bundled `food_data.csv` with the four macro columns (sourced from the same
  USDA FoodData Central CC0 nutrient IDs already used for energy — 203/204/205/291), and
  the `ResolutionCache` / candidate retrieval path to carry them.
- Store the four macro values on `FoodEntry`, nullable to accommodate rows resolved before
  this change and entries whose macro estimate genuinely fails (mirrors the existing
  nullable-`grams` precedent for stated-kcal entries).
- Add a `macros` value to the report-topic classification, teach the report-extraction
  prompt to recognize a macro-distribution request, and add a report branch that computes
  total and average grams of each macro over the period and renders a distribution chart
  (stacked bar per day, one color per macro).
- Update the disclaimers in `telegram/handlers.py`, `reporting/dietician.py` and
  `advice/agent.py` that currently state macros are not tracked, since they will no longer
  be accurate.
- Backfill macro grams for existing `FoodEntry` rows via an admin/CLI command that re-runs
  the hybrid resolution path per distinct historical food description and updates matching
  entries' macro columns, without touching their already-stored kcal.

## Capabilities

### New Capabilities

(none — this extends the existing food-logging and reporting capabilities rather than
introducing a new one)

### Modified Capabilities

- `food-logging`: food entries additionally resolve and store protein/fat/carbohydrate/fiber
  grams, through the same hybrid resolution and caching rules as kcal.
- `reporting`: report-topic classification recognizes a `macros` topic, a macro report exists
  with defined contents and a distribution chart, and the "no macronutrient data" caveat is
  retired now that the data exists.
- `help-and-welcome`: the help text now states that macronutrients are tracked, replacing
  sodium/sugar as the "not tracked" example.
- `advice-agent`: the meal-suggestion and absent-data requirements are corrected to no longer
  justify their qualitative-only, no-gram-amount behavior by claiming macros aren't tracked
  at all — that behavior is kept (per explicit decision) but reframed as a deliberate
  conversational-tone choice, and a new scenario covers a stray conversational macro
  question redirecting the user to the macro report.
- `dietician-reviews`: same reframing for the month/year review's qualitative macro-balance
  recommendation.

## Impact

- `src/calobot/persistence/models.py` (`FoodEntry`, `ResolutionCache`) — new nullable macro
  columns.
- `src/calobot/persistence/migrations/` — new Alembic revision (no `create_all`).
- `src/calobot/data/food_data.csv`, `src/calobot/data/DATA_SOURCES.md` — new macro columns,
  provenance notes for the additional USDA nutrient IDs.
- `src/calobot/persistence/candidates.py`, `src/calobot/food/resolver.py` — candidate rows
  and resolution results carry macros; the LLM estimate schema gains macro fields.
- `src/calobot/ingestion/schemas.py`, `src/calobot/ingestion/extractors.py`,
  `src/calobot/ingestion/pipeline.py` — `ReportExtraction.topic` enum, `REPORT_PROMPT`, and
  `_handle_report` dispatch.
- `src/calobot/reporting/charts.py` — new macro-distribution chart renderer.
- `src/calobot/reporting/dietician.py`, `src/calobot/advice/agent.py`,
  `src/calobot/telegram/handlers.py` — remove or update the "macros not tracked" language.
- A new backfill entry point (CLI script or admin command, following whatever pattern the
  project already uses for one-off maintenance operations) that re-resolves macros for
  historical `FoodEntry` rows.
