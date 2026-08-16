# weight-logging Specification

## Purpose

Records the user's body weight from conversational messages, normalizing the many ways people state it into a precise value. Weight is both the outcome the product tracks and an input to the calorie budget and to activity energy, so its accuracy and its history matter throughout the system.

## Requirements

### Requirement: Weight entry contents

The system SHALL store, for each weight entry, the value in kilograms, the day it refers to in the Europe/Rome timezone, the timestamp it was recorded, and the user it belongs to.

#### Scenario: Explicit weight

- **WHEN** a user writes "oggi peso 78kg"
- **THEN** the system stores a weight entry of 78.0 kg for the current day and confirms it

### Requirement: Conversational value normalization

The system SHALL normalize conversational statements of weight into a precise numeric value in kilograms, including fractional forms expressed in words, values stated without a unit, and values stated as a change relative to the previous entry.

#### Scenario: Fractional form in words

- **WHEN** a user writes "78 e mezzo"
- **THEN** the system stores 78.5 kg

#### Scenario: Value without a unit

- **WHEN** a user writes "stamattina 77,4"
- **THEN** the system stores 77.4 kg

#### Scenario: Relative change

- **WHEN** a user writes a change relative to their last recorded weight, such as "ho perso mezzo chilo"
- **THEN** the system computes the resulting weight from the most recent entry, stores it, and states the resulting absolute value in its confirmation

#### Scenario: Relative change with no previous weight

- **WHEN** a user states a relative change and has no previously recorded weight
- **THEN** the system explains that it has no starting value and asks for the current weight

### Requirement: Plausibility validation

The system SHALL reject a weight outside the plausible human range, and SHALL ask the user to confirm a weight that differs from their most recent entry by an implausible amount for the elapsed time rather than storing it silently.

#### Scenario: Value outside the plausible range

- **WHEN** a user states a weight below 30 kg or above 400 kg
- **THEN** the system rejects it, explains the accepted range, and stores nothing

#### Scenario: Implausible jump

- **WHEN** a stated weight differs from the most recent entry by an amount implausible for the days elapsed
- **THEN** the system asks the user to confirm the value before storing it

### Requirement: One weight per day

The system SHALL keep at most one weight entry per user per day. A second weight stated for a day that already has one SHALL replace it, and the replacement SHALL be stated in the confirmation.

#### Scenario: Second weighing on the same day

- **WHEN** a user states a weight for a day that already has a recorded weight
- **THEN** the existing entry is replaced by the new value and the system says that it has replaced the earlier value

### Requirement: Weight for a past day

The system SHALL honour an explicit day stated with a weight and record the entry against that day.

#### Scenario: Retroactive weight

- **WHEN** a user writes "ieri pesavo 78,2"
- **THEN** the entry is recorded against the previous day rather than today

### Requirement: Effects of a new weight

The system SHALL recompute the daily calorie budget when a new weight is recorded, and SHALL use the most recent weight for subsequent activity energy computations.

#### Scenario: Budget follows the new weight

- **WHEN** a weight entry is stored or replaced
- **THEN** the daily calorie budget is recomputed from the updated weight

#### Scenario: Goal reached

- **WHEN** a recorded weight reaches or passes the user's peso obiettivo
- **THEN** the system tells the user the goal has been reached and offers to set a new goal or switch to maintenance
