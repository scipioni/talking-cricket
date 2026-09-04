## ADDED Requirements

### Requirement: Food entry macro-nutrient contents

The system SHALL resolve and store, for each food entry, the protein, fat, carbohydrate
and fiber content in grams, alongside its kilocalories. These values SHALL be derived from
the same resolved portion (grams, or back-derived grams when only kcal was stated) used to
compute the entry's kilocalories, so a doubled portion doubles both energy and macros
consistently.

When a macro value cannot be resolved for a food — because the hybrid resolution path
(cache, bundled table, language model estimate) yields no value for it — the entry SHALL
still be stored, with that macro value recorded as absent rather than the entry being
blocked or a zero substituted.

#### Scenario: Simple ingredient with an explicit quantity

- **WHEN** a user writes "ho mangiato 10g di noci"
- **THEN** the system stores a food entry whose protein, fat, carbohydrate and fiber grams
  are scaled to the 10 gram portion, alongside its kilocalories

#### Scenario: Calorie value stated directly

- **WHEN** a user writes "100kcal di melanzane sott'olio", stating a calorie amount rather
  than a quantity
- **THEN** the entry's macro grams are derived from the same back-derived gram quantity used
  for display, when an energy density was resolved, or recorded as absent when it was not

#### Scenario: A macro value cannot be resolved

- **WHEN** the hybrid resolution path yields kilocalories for a food but no value for one of
  its macros
- **THEN** the entry is stored with kilocalories as normal and that macro recorded as absent,
  rather than the entry being rejected or a zero value assumed

### Requirement: Macro-nutrient resolution follows the hybrid energy path

The system SHALL resolve macro-nutrient values per 100 grams through the same ordered path
as energy: the resolution cache, then the bundled food composition table, then the language
model. A macro value resolved from the bundled table or an LLM estimate SHALL be cached
alongside the energy value under the same normalized food key, so a later lookup of the same
food reuses all of them together.

#### Scenario: Ingredient present in the table

- **WHEN** the food names an ingredient with a matching row in the food composition table
- **THEN** its per-100g macro values are taken from that row, the same row used for energy

#### Scenario: Composite dish absent from the table

- **WHEN** the food names a composite dish with no matching row
- **THEN** its per-100g macro values are estimated by the language model alongside the energy
  estimate

#### Scenario: Repeated dish yields the same macro values

- **WHEN** a user logs the same dish on two different days with the same portion
- **THEN** both entries record the same macro grams, because both draw on the same cached
  per-100g resolution used for kilocalories
