# entry-correction Specification

## Purpose

Lets a user fix an entry that was already stored, whether the language model misread the message or the user simply got it wrong. Because a tracker people cannot correct is a tracker people stop trusting, this capability also defines how corrections are targeted unambiguously and how deleted data affects reports.

## Requirements

### Requirement: Undo the most recent entry

The system SHALL provide a command that deletes the user's most recently created entry of any type and confirms what was removed.

#### Scenario: Undo after logging

- **WHEN** a user issues the undo command after an entry was stored
- **THEN** the system deletes that entry and confirms which entry it removed

#### Scenario: Nothing to undo

- **WHEN** a user issues the undo command and has no entries
- **THEN** the system says there is nothing to undo and changes nothing

### Requirement: Amending the most recent entry by message

The system SHALL interpret a message classified as a correction and referring to no specific earlier entry as an amendment of the user's most recent entry, apply the stated change, recompute any derived values, and confirm the updated entry.

#### Scenario: Correcting a quantity

- **WHEN** a user writes "no erano 20g" immediately after an entry of 10 g was stored
- **THEN** the system updates that entry to 20 g, recomputes its kilocalories, and confirms the corrected values

#### Scenario: Correcting the food itself

- **WHEN** a user corrects which food was eaten rather than the quantity
- **THEN** the system re-resolves the energy for the corrected food and confirms the updated entry

#### Scenario: Ambiguous between a correction and a new entry

- **WHEN** a message could be read either as a correction of the previous entry or as a new entry
- **THEN** the system asks the user which was meant before changing or storing anything

### Requirement: Deterministic targeting of an entry

Every confirmation the system sends for a stored entry SHALL carry controls that identify that specific entry, allowing the user to modify or delete it directly. The system SHALL also treat a reply to a confirmation message as referring to the entry that confirmation created.

#### Scenario: Deleting through the confirmation controls

- **WHEN** a user activates the delete control on an earlier confirmation message
- **THEN** the system deletes exactly that entry, regardless of how many entries were stored afterwards, and confirms the deletion

#### Scenario: Replying to an earlier confirmation

- **WHEN** a user replies to the confirmation message of an earlier entry with a correction
- **THEN** the system applies the correction to that entry rather than to the most recent one

#### Scenario: Modifying through the confirmation controls

- **WHEN** a user activates the modify control on a confirmation message
- **THEN** the system asks what should change for that entry and applies the answer to it

### Requirement: Corrections are limited to targeted entries

The system SHALL support correcting only the most recent entry or an entry targeted through confirmation controls or a reply. When a user refers to an earlier entry in free text without such targeting, the system SHALL explain that the entry must be targeted through its confirmation message and SHALL change nothing.

#### Scenario: Free text reference to an older entry

- **WHEN** a user writes a correction referring to an earlier entry in free text, such as "ieri a pranzo non era pasta ma riso"
- **THEN** the system explains how to target that entry and makes no change

### Requirement: Soft deletion

The system SHALL mark deleted entries as deleted rather than removing them, and SHALL exclude deleted entries from every report, statistic and chart. Permanent removal of all of a user's data on request SHALL remain unaffected by this requirement.

#### Scenario: Deleted entry excluded from reports

- **WHEN** an entry is deleted and a report covering its period is produced
- **THEN** the deleted entry contributes nothing to any total, average or chart in that report

#### Scenario: Deleting an already deleted entry

- **WHEN** a user activates the delete control on an entry that has already been deleted
- **THEN** the system says the entry is already deleted and changes nothing

### Requirement: Corrections propagate to derived values

The system SHALL recompute all values derived from an entry when that entry is corrected or deleted, including the daily calorie budget when the corrected entry is a weight.

#### Scenario: Correcting the latest weight

- **WHEN** a user corrects their most recent weight entry
- **THEN** the daily calorie budget is recomputed from the corrected weight
