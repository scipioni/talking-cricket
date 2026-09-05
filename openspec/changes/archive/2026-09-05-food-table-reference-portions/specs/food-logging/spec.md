## MODIFIED Requirements

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
