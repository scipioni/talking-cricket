## Purpose

Records physical activity the user reports in conversation and quantifies its energy cost from a metabolic equivalent table, giving the reports a movement dimension alongside intake and weight. It is deliberately informational: the daily calorie budget already accounts for habitual activity, so logged activity must never be added on top of it.

## ADDED Requirements

### Requirement: Activity entry contents

The system SHALL store, for each activity entry, the activity as understood, the duration in minutes, the metabolic equivalent value used, the computed energy expenditure in kilocalories, the timestamp, and the user it belongs to.

#### Scenario: Activity with an explicit duration

- **WHEN** a user writes "ho fatto una camminata di mezz'ora"
- **THEN** the system stores an activity entry of 30 minutes with its computed energy expenditure and confirms both to the user

#### Scenario: Duration missing

- **WHEN** a user reports an activity without a duration
- **THEN** the system asks how long it lasted and does not store an entry until it is known

### Requirement: Energy expenditure computation

The system SHALL compute activity energy expenditure as the metabolic equivalent value multiplied by the user's most recently recorded weight in kilograms and by the duration in hours. The metabolic equivalent value SHALL be taken from a bundled table of activities; candidate rows SHALL be retrieved by name similarity and the language model SHALL select the best matching row.

#### Scenario: Computation uses current weight

- **WHEN** an activity is logged after the user has recorded a new weight
- **THEN** the energy expenditure is computed using the most recent weight

#### Scenario: Activity absent from the table

- **WHEN** no row in the table matches the reported activity
- **THEN** the system obtains a metabolic equivalent estimate from the language model and records that the value is an estimate

### Requirement: Intensity clarification

The system SHALL ask for intensity when the reported activity spans metabolic equivalent values that differ materially and no intensity was stated, offering the common intensities as tappable options.

#### Scenario: Ambiguous intensity

- **WHEN** a user reports an activity such as "camminata" whose plausible intensities differ materially in metabolic equivalent
- **THEN** the system asks at what intensity it was performed, offering the common intensities as options

#### Scenario: Intensity stated

- **WHEN** a user reports an activity together with its intensity or pace
- **THEN** the system selects the matching row without asking

### Requirement: Activity does not alter the calorie budget

The system SHALL NOT increase, decrease or otherwise modify the user's daily calorie budget on the basis of logged activity, because the budget already includes the activity factor from the user's profile. Confirmations and reports SHALL present activity energy as information and SHALL NOT describe it as calories earned, gained or available.

#### Scenario: Budget unchanged after logging activity

- **WHEN** a user logs an activity on a given day
- **THEN** that day's calorie budget is identical to what it was before the activity was logged

#### Scenario: Wording of the confirmation

- **WHEN** the system confirms a logged activity
- **THEN** it reports the estimated energy expenditure as information and does not state or imply that the user may eat more

### Requirement: Time of activity

The system SHALL record activity entries against the moment of the activity in the Europe/Rome timezone, defaulting to the time the message was received, and SHALL honour an explicit time or day stated in the message.

#### Scenario: Retroactive activity

- **WHEN** a user writes "ieri ho corso 40 minuti"
- **THEN** the entry is recorded against the previous day
