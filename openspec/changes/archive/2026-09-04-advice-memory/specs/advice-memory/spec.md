## Purpose

Keeps a durable record of the advice the bot has given a user — what was suggested,
when, in response to what, and through which surface — and, where logged data can
settle it, whether that advice was subsequently followed, so later advice can build on
earlier advice instead of repeating it or ignoring whether it worked.

## ADDED Requirements

### Requirement: Advice is recorded by the code that emits it

Whenever the system produces the dietician review's actionable recommendation, the
daily calorie report's rest-of-day advice, or a meal suggestion from the advice agent,
it SHALL record that advice: its text, the surface it came from, and a situation
identifier describing what prompted it (such as the report period or the suggestion
mode). The record SHALL be written by the deterministic code that emits the advice,
never inferred from the model narrating what it did.

#### Scenario: Dietician review tip is recorded

- **WHEN** a dietician review is generated and includes its actionable recommendation
- **THEN** a record is stored capturing the recommendation text, the surface
  "dietician_review", and the report period

#### Scenario: Daily rest-of-day advice is recorded

- **WHEN** a daily calorie report includes rest-of-day advice
- **THEN** a record is stored capturing the advice text and the surface "daily_advice"

#### Scenario: Advice-agent meal suggestion is recorded

- **WHEN** the advice agent answers with a meal or recipe suggestion
- **THEN** a record is stored capturing the suggestion text, the surface
  "advice_agent", and the suggestion situation that was derived for it

#### Scenario: A plain question-and-answer is not recorded as advice

- **WHEN** the advice agent answers a question that states or explains the user's own
  data without suggesting anything
- **THEN** no advice record is created for that answer

### Requirement: Outcome is determined deterministically where possible

For a recorded piece of advice whose topic can be matched to a signal the system
already computes — meal timing or logging consistency — the system SHALL determine,
once enough subsequent data exists, whether the user's logged behaviour moved in the
direction the advice encouraged. The outcome SHALL be one of: followed, not followed,
or undetermined. An outcome SHALL NOT be guessed or inferred by a language model; it
SHALL be computed from logged entries using the same deterministic signals the
reporting and advice capabilities already produce. Advice whose topic cannot be
matched to a computable signal SHALL remain undetermined permanently, rather than
receiving a guessed outcome.

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

### Requirement: A recent unresolved actionable tip is not repeated verbatim

Before the dietician review or the daily calorie report produces a new actionable
recommendation, the system SHALL check whether the user already has a recent
recommendation of the same kind whose outcome is still undetermined, and SHALL ensure
the new recommendation is not the same text repeated verbatim.

#### Scenario: A recent unresolved tip exists

- **WHEN** a new dietician review is generated and the user was given an actionable
  recommendation in the last review of the same kind, whose outcome is still
  undetermined
- **THEN** the new recommendation is not the same text repeated verbatim

#### Scenario: The prior tip was already resolved

- **WHEN** the user's most recent recommendation of the same kind already has a
  determined outcome (followed or not followed)
- **THEN** a new recommendation may repeat the same idea if it is still the most
  relevant one

### Requirement: The advice agent may read prior advice

The system SHALL give the advice agent a read-only tool over the advice record, so
that an answer can reference what was already suggested and whether it was acted on.
This tool SHALL be read-only like every other tool available to the agent.

#### Scenario: User asks whether a suggestion was useful

- **WHEN** a user asks something like "il consiglio di ieri ha funzionato?"
- **THEN** the agent retrieves the relevant advice record and its outcome rather than
  guessing or re-deriving it from other tools

### Requirement: No-retention mode suppresses advice recording

While a chat is in no-retention mode, no advice record SHALL be created or persisted,
consistent with how no-retention mode already suppresses every other write.

#### Scenario: Advice given while no-retention mode is active

- **WHEN** the dietician review, the daily advice or the advice agent produces advice
  while a chat is in no-retention mode
- **THEN** no advice record is stored for it

### Requirement: Advice records are removed by /cancellami

A user's advice records SHALL be permanently removed when the user's data is deleted
via /cancellami, along with every other kind of stored data.

#### Scenario: Deleting all data removes advice records

- **WHEN** a user runs /cancellami and confirms
- **THEN** their advice records are permanently deleted along with their profile and
  logged entries
