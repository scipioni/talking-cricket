## MODIFIED Requirements

### Requirement: Profile inspection, editing and deletion

The system SHALL let a user view their current profile and derived budget, change any single field, and delete all their data permanently. A field SHALL be changeable by stating the new value in ordinary conversation, without a command and without repeating onboarding. A change stated this way SHALL be confirmed by the user before it is applied, and the request for confirmation SHALL state the field, the value it currently holds, the proposed value, and the resulting change to the daily calorie budget. No field SHALL be modified until the change is confirmed. Deleting all data SHALL also permanently remove every advice record kept for the user and the user's nudge preference.

The profile view SHALL include whether unprompted nudges are currently enabled for
the user, and this preference SHALL default to disabled for every user unless they
have explicitly enabled it.

#### Scenario: Viewing the profile

- **WHEN** a user asks to see their profile
- **THEN** the system reports every stored field, the current daily budget, and
  whether nudges are enabled

#### Scenario: Changing a field in conversation

- **WHEN** a user states a new value for a profile field, such as "ora il mio peso obiettivo è 74kg" or "la mia data di nascita è 16/5/72"
- **THEN** the system asks the user to confirm, stating the field, its current value, the proposed value and how the daily budget would change, and offers the answers as tappable options

#### Scenario: Confirming a change

- **WHEN** a user confirms a proposed profile change
- **THEN** the field is updated, the daily budget is recomputed from the new value, and the system confirms what changed

#### Scenario: Declining a change

- **WHEN** a user declines a proposed profile change
- **THEN** no field is modified and the system says that nothing was changed

#### Scenario: A stated value that cannot be interpreted

- **WHEN** the value stated for the named field cannot be interpreted, such as a birth date that is not a date
- **THEN** the system asks for the value again rather than storing a guess, and no field is modified

#### Scenario: An edit that breaches a safety limit

- **WHEN** a user states a peso obiettivo implying a body mass index below 18.5
- **THEN** the system refuses it as it does during onboarding, explains why, and leaves the stored goal unchanged

#### Scenario: Current weight is a measurement, not a profile edit

- **WHEN** a user states their current weight, such as "peso 88 kg"
- **THEN** the message is handled as a weight measurement by the weight-logging capability rather than as a profile edit

#### Scenario: Deleting all data

- **WHEN** a user requests deletion of their data and confirms the request
- **THEN** the system permanently removes the user's profile, all their logged entries, all their advice records, and their nudge preference, and confirms the deletion

#### Scenario: Deleting all data removes advice records

- **WHEN** a user runs /cancellami and confirms
- **THEN** no advice record for that user remains in storage

#### Scenario: New user defaults to nudges disabled

- **WHEN** a user completes onboarding without ever mentioning nudges
- **THEN** their nudge preference is disabled, and it stays disabled until they
  explicitly enable it
