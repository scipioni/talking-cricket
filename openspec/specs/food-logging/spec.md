# food-logging Specification

## Purpose

Records what the user ate and converts it into calories in a way that is consistent over time, so that a report reflects real changes in eating rather than the variance of a language model. It covers both simple ingredients that exist in a food composition table and composite dishes that do not.

## Requirements

### Requirement: Food entry contents

The system SHALL store, for each food entry, the description as understood, the resolved energy in kilocalories, the energy per 100 grams used, the provenance of that energy value, the timestamp of consumption, and the user it belongs to. The system SHALL store the resolved quantity in grams when it is known, or an explicit unknown-quantity marker when it is not.

#### Scenario: Simple ingredient with an explicit quantity

- **WHEN** a user writes "ho mangiato 10g di noci"
- **THEN** the system stores a food entry of 10 grams with the corresponding kilocalories and confirms both to the user

#### Scenario: Several foods in one message

- **WHEN** a user writes a message listing more than one food, such as "a pranzo pasta al pesto e una mela"
- **THEN** the system creates a separate entry for each food and confirms each one

#### Scenario: Calorie value stated directly

- **WHEN** a user writes "100kcal di melanzane sott'olio", stating a calorie amount rather than a quantity
- **THEN** the system stores an entry whose kilocalories equal the stated 100 kcal, not a value computed from an assumed gram quantity

### Requirement: Quantity resolution

The system SHALL resolve quantities expressed in grams, in common household measures, or as counts of a countable item, into grams. When a quantity cannot be resolved and no calorie value was stated directly, the entry SHALL NOT be stored and the clarification loop of the message-ingestion capability SHALL be used.

The gram options offered for an unresolvable quantity SHALL be food-specific whenever a food-specific scale exists, in this order: multiples of the typical unit weight for a countable food; the reference portions recorded for that food in the bundled food table; portion estimates supplied by the extraction; the generic scale only as a last resort. Options shown with the question SHALL be the options the answer is mapped against.

#### Scenario: Quantity given by count

- **WHEN** a user writes "due mele"
- **THEN** the system resolves the count to a weight in grams using a typical unit weight and states the assumed weight in its confirmation

#### Scenario: Count of a single item named without a separate unit

- **WHEN** a user writes "mangio una pesca", naming the counted food itself rather than a separate unit such as "fetta" or "cucchiaio"
- **THEN** the food's own name is used to look up the typical unit weight, and the entry is stored without asking for a portion size

#### Scenario: Count of an item absent from the unit weight table

- **WHEN** a user writes a count of a countable food whose unit weight is not in the bundled table
- **THEN** the system resolves it using a typical unit weight supplied by the extraction, rather than discarding the stated count and asking for a portion size

#### Scenario: Quantity not resolvable

- **WHEN** a user writes a food with no resolvable quantity
- **THEN** the system asks for the portion size instead of storing the entry, offering gram options in the order: unit-weight multiples for a countable food, the food table's reference portions, the extraction's estimates, the generic scale

#### Scenario: A condiment-scale food asks with its own scale

- **WHEN** a user writes a vague quantity for a condiment or base vegetable whose reference portions are in the bundled table, such as "ho mangiato cipolla"
- **THEN** the portion options offered reflect that food's reference portions from the table, not the generic scale meant for a plated dish

#### Scenario: A household measure covers foods of very different typical sizes

- **WHEN** a user writes a vague quantity for a condiment such as "un cucchiaio di maionese"
- **THEN** the portion options offered reflect plausible gram amounts for a condiment rather than the generic scale meant for a plated dish

#### Scenario: The table knows the food but the extraction guessed anyway

- **WHEN** a vague-portion question arises for a food whose reference portions are in the bundled table, and the extraction also supplied its own estimates
- **THEN** the options shown come from the table, because the bundled table is authoritative over the model's judgement

#### Scenario: The answer maps against what was shown

- **WHEN** a user taps one of the gram options offered with a vague-portion question
- **THEN** the tapped label resolves to the same grams it displayed, even though the
  lookup that produced the options cannot run again while applying the answer

### Requirement: Calorie value stated directly

The system SHALL recognize when a user states a calorie amount for a food instead of, or in addition to, a quantity. When a calorie value is stated, the system SHALL use that value as the entry's kilocalories directly, rather than computing kilocalories forward from a resolved or assumed gram quantity.

#### Scenario: Stated kcal takes precedence over an assumed quantity

- **WHEN** a user writes "100kcal di melanzane sott'olio", giving only a calorie amount and no quantity
- **THEN** the entry's kilocalories equal 100, and the system does not treat "100" as a gram quantity

#### Scenario: Estimated grams shown alongside a stated calorie value

- **WHEN** a calorie value was stated directly and the system can resolve an energy density (kilocalories per 100 grams) for the food
- **THEN** the system back-derives an approximate gram quantity from the stated kilocalories and that density, stores it, and marks it in the confirmation as approximate rather than as a directly stated quantity

#### Scenario: Energy density cannot be resolved

- **WHEN** a calorie value was stated directly but the food's energy density cannot be resolved, or resolves to zero
- **THEN** the entry is stored with the stated kilocalories and an explicit unknown-quantity marker in place of grams, rather than the system dividing by zero or fabricating a gram amount

#### Scenario: Confirmation distinguishes a stated calorie value

- **WHEN** an entry's kilocalories came from a value the user stated directly
- **THEN** the confirmation shown to the user makes clear the calories were as stated, rather than presenting grams and kilocalories as if both were derived from a quantity

### Requirement: Hybrid energy resolution

The system SHALL resolve the energy content of a food by consulting, in order: the resolution cache, then the bundled food composition table, then the language model. When consulting the food composition table, the system SHALL retrieve candidate rows by name similarity and SHALL use the language model to select the best matching row or to report that none of the candidates fits. When no row fits, the system SHALL obtain an estimate of kilocalories per 100 grams from the language model.

#### Scenario: Ingredient present in the table

- **WHEN** the food names an ingredient with a matching row in the food composition table
- **THEN** the energy is taken from that row and the entry's provenance records that the value came from the table

#### Scenario: Composite dish absent from the table

- **WHEN** the food names a composite dish such as "pasta al pesto" with no matching row
- **THEN** the energy is estimated by the language model and the entry's provenance records that the value is an estimate

#### Scenario: Estimate disclosed to the user

- **WHEN** an entry's energy came from a language model estimate
- **THEN** the confirmation shown to the user identifies the value as a stima

### Requirement: Food descriptions presented in Italian

The system SHALL store and present every food description in Italian, regardless of the language of the underlying food composition table row it was matched against. A user SHALL never see the source row's name when that name is not Italian.

#### Scenario: Matched row is not in Italian

- **WHEN** a food is resolved by matching a row whose name is not in Italian
- **THEN** the confirmation and any report show the food in Italian, as the user expressed it

### Requirement: Resolution cache and consistency

The system SHALL cache each resolved energy per 100 grams against a normalized form of the food description, together with its provenance, and SHALL reuse the cached value for later matching descriptions. The same food SHALL therefore always yield the same energy per 100 grams for the same user.

#### Scenario: Repeated dish yields the same energy density

- **WHEN** a user logs the same dish on two different days with the same portion
- **THEN** both entries record the same kilocalories

#### Scenario: Description varies but normalizes to the same food

- **WHEN** a user writes the same food with different capitalization, spacing or plural form
- **THEN** the cached value is reused rather than resolved again

### Requirement: Preparation affecting energy

The system SHALL take account of a stated preparation method when it materially changes energy content, and SHALL ask for the preparation when the difference between plausible preparations is material and none was stated.

#### Scenario: Preparation stated

- **WHEN** a user writes a food together with a preparation such as "fritto" or "bollito"
- **THEN** the resolved energy reflects that preparation

#### Scenario: Preparation material but unstated

- **WHEN** a food's plausible preparations differ materially in energy and none was stated
- **THEN** the system asks which preparation was used before storing the entry, offering the preparations that apply to that specific food when the extraction supplied them, and a generic list otherwise

#### Scenario: A food whose preparations are not the generic ones

- **WHEN** the system asks how an egg was prepared
- **THEN** the options offered describe ways an egg is actually cooked rather than a fixed fry/boil/bake/grill list

### Requirement: Time of consumption

The system SHALL record food entries against the moment of consumption in the Europe/Rome timezone, defaulting to the time the message was received, and SHALL honour an explicit time or day stated in the message.

#### Scenario: Retroactive entry

- **WHEN** a user writes "ieri a cena ho mangiato una pizza"
- **THEN** the entry is recorded against the previous day

#### Scenario: Explicit time stated

- **WHEN** a user writes "ho mangiato una mela alle 15 di ieri"
- **THEN** the entry is recorded at 15:00 Europe/Rome on the previous day

#### Scenario: No time stated

- **WHEN** a user logs a food without stating when
- **THEN** the entry is recorded at the time the message was received

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
