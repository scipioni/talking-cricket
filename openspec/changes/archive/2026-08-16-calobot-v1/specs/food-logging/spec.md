## Purpose

Records what the user ate and converts it into calories in a way that is consistent over time, so that a report reflects real changes in eating rather than the variance of a language model. It covers both simple ingredients that exist in a food composition table and composite dishes that do not.

## ADDED Requirements

### Requirement: Food entry contents

The system SHALL store, for each food entry, the description as understood, the resolved quantity in grams, the resolved energy in kilocalories, the energy per 100 grams used, the provenance of that energy value, the timestamp of consumption, and the user it belongs to.

#### Scenario: Simple ingredient with an explicit quantity

- **WHEN** a user writes "ho mangiato 10g di noci"
- **THEN** the system stores a food entry of 10 grams with the corresponding kilocalories and confirms both to the user

#### Scenario: Several foods in one message

- **WHEN** a user writes a message listing more than one food, such as "a pranzo pasta al pesto e una mela"
- **THEN** the system creates a separate entry for each food and confirms each one

### Requirement: Quantity resolution

The system SHALL resolve quantities expressed in grams, in common household measures, or as counts of a countable item, into grams. When a quantity cannot be resolved, the entry SHALL NOT be stored and the clarification loop of the message-ingestion capability SHALL be used.

#### Scenario: Quantity given by count

- **WHEN** a user writes "due mele"
- **THEN** the system resolves the count to a weight in grams using a typical unit weight and states the assumed weight in its confirmation

#### Scenario: Quantity not resolvable

- **WHEN** a user writes a food with no resolvable quantity
- **THEN** the system asks for the portion size instead of storing the entry

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
- **THEN** the system asks which preparation was used before storing the entry

### Requirement: Time of consumption

The system SHALL record food entries against the moment of consumption in the Europe/Rome timezone, defaulting to the time the message was received, and SHALL honour an explicit time or day stated in the message.

#### Scenario: Retroactive entry

- **WHEN** a user writes "ieri a cena ho mangiato una pizza"
- **THEN** the entry is recorded against the previous day

#### Scenario: No time stated

- **WHEN** a user logs a food without stating when
- **THEN** the entry is recorded at the time the message was received
