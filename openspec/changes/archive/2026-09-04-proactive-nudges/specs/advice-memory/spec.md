## MODIFIED Requirements

### Requirement: Outcome is determined deterministically where possible

For a recorded piece of advice whose topic can be matched to a signal the system
already computes — meal timing or logging consistency — the system SHALL determine,
once enough subsequent data exists, whether the user's logged behaviour moved in the
direction the advice encouraged. The outcome SHALL be one of: followed, not followed,
or undetermined. An outcome SHALL NOT be guessed or inferred by a language model; it
SHALL be computed from logged entries using the same deterministic signals the
reporting and advice capabilities already produce. Advice whose topic cannot be
matched to a computable signal SHALL remain undetermined permanently, rather than
receiving a guessed outcome. An advice record whose outcome is still undetermined
after enough time has passed is a candidate signal the proactive-nudges capability
may use to prompt about it, but recording and resolving the outcome remains
independent of whether any nudge is ever sent for it.

#### Scenario: Meal-timing advice later followed

- **WHEN** advice about eating earlier in the day was recorded, and the meal-timing
  signal for the days afterward shows the typical last-meal hour moved earlier by a
  meaningful margin
- **THEN** the record's outcome is set to followed

#### Scenario: Logging-consistency advice later ignored

- **WHEN** advice about logging more consistently was recorded, and the logging
  consistency signal for the days afterward shows no improvement
- **THEN** the record's outcome is set to not followed

#### Scenario: Not enough subsequent data yet

- **WHEN** an outcome-checkable piece of advice was recorded too recently for the
  relevant signal to have enough data behind it
- **THEN** the outcome remains undetermined rather than being decided early

#### Scenario: Advice with no matching signal

- **WHEN** a recorded piece of advice does not concern meal timing or logging
  consistency
- **THEN** its outcome stays undetermined indefinitely, and this is not treated as a
  failure to compute anything

#### Scenario: An unresolved record becomes a nudge candidate

- **WHEN** an advice record remains undetermined for long enough that
  proactive-nudges considers it a candidate signal
- **THEN** using it as a nudge candidate does not change how or when its own
  outcome gets determined
