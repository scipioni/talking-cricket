## MODIFIED Requirements

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

- **WHEN** a user writes a food with no resolvable quantity and no stated calorie value
- **THEN** the system asks for the portion size instead of storing the entry, offering small/medium/generous gram options scaled to that specific food when the extraction supplied them, or a generic 80/120/180g scale otherwise

#### Scenario: A household measure covers foods of very different typical sizes

- **WHEN** a user writes a vague quantity for a condiment such as "un cucchiaio di maionese"
- **THEN** the portion options offered reflect plausible gram amounts for a condiment rather than the generic scale meant for a plated dish

## ADDED Requirements

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
