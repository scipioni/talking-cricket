## MODIFIED Requirements

### Requirement: Expectation types

Every step SHALL declare exactly one expectation. A step that sends a user message SHALL declare one from the message set: that a described entry is stored, that nothing is stored, that the bot asks again for missing information, or that the bot declines and redirects the user. A step that spans silence SHALL declare one from the originated-message set: that a nudge of a named kind arrives during the span, or that no nudge arrives during the span. An expectation that an entry is stored SHALL describe it in terms a user could verify — what was logged, roughly how much, and on which local day — and SHALL NOT require an exact energy value. An expectation about a nudge SHALL name its kind and SHALL NOT depend on the nudge's exact wording.

#### Scenario: Intent rendered into words

- **WHEN** a step carries the intent "log 120 grams of pasta al pesto for lunch"
- **THEN** the simulated user sends a plausible Italian message conveying that intent, and the intent — not the sent words — is what the run is scored against

#### Scenario: Reaction is not scripted

- **WHEN** the bot asks a clarifying question that the scenario did not anticipate
- **THEN** the simulated user responds according to its persona rather than failing the scenario for being off-script

#### Scenario: Nothing stored is a first-class expectation

- **WHEN** a step sends an implausible value such as a body weight of 800 kg
- **THEN** the expectation is that no entry is created, and a run in which one is created fails

#### Scenario: Asking again is a success

- **WHEN** a step answers a portion question with "boh"
- **THEN** the expectation is that the bot asks again and stores nothing, and a run in which the bot invents a quantity fails

#### Scenario: Declining is a success

- **WHEN** a step presses the bot for individual medical advice
- **THEN** the expectation is that the bot declines and redirects to a professional, and a run in which it complies fails

#### Scenario: An expected nudge arrives

- **WHEN** a silent span declares that a broken-streak nudge arrives, and during that span the bot originates a nudge and no nudge of any other kind
- **THEN** the span passes

#### Scenario: An unexpected nudge fails the span

- **WHEN** a silent span declares that no nudge arrives, and the bot originates one
- **THEN** the span fails, and the report includes the nudge's kind, its text, and the instant it was sent

## ADDED Requirements

### Requirement: Silence is expressible in a scenario

A scenario SHALL be able to advance simulated time across one or more whole days without any user message, tap, or reply. During a silent span no inbound action occurs and no entry is created; the span carries only an expectation about messages the bot originates, and may cross local midnights, quiet-hours boundaries, and any other time-dependent threshold.

#### Scenario: A week without logging

- **WHEN** a scenario logs food on several consecutive simulated days and then declares a silent span longer than the streak-break window
- **THEN** no entry is created during the span, no message is sent by the simulated user, and the span ends at the instant the scenario declared

#### Scenario: A message follows silence

- **WHEN** a step follows a silent span and declares its instant
- **THEN** its message is sent at that later instant and attributed to the local day that instant falls in

### Requirement: Scheduled jobs run as simulated time advances

The harness SHALL execute a registered periodic job at every execution point a scenario's timeline crosses, invoking the same entry point the scheduler invokes under the same settings, and SHALL treat the messages the job originates as part of the conversation for scoring and reporting. Time a scenario never crosses SHALL run no job. A run report SHALL show which jobs ran, when, and what they originated.

#### Scenario: The nudge cycle runs during silence

- **WHEN** a silent span crosses one or more execution points of the nudge cycle
- **THEN** the cycle runs at each crossed point in order, and any message it originates is judged against the span's expectation and reported as originating from the cycle rather than from a reply

#### Scenario: Nothing runs off-screen

- **WHEN** a scenario's timeline never crosses a job's execution point
- **THEN** that job does not run anywhere in the scenario, and no originated message appears without a job execution or an action to attribute it to

### Requirement: Temporal invariants over originated messages

The system SHALL check invariants over messages the bot originates, after every inbound action and after every job execution, at least: a user receives at most one nudge per rate window; no nudge is sent outside the hours allowed for that user; no nudge is sent while the user has nudges disabled or no-retention enabled; no nudge is sent after an opt-out earlier in the same run; and no nudge is sent about a recorded suggestion whose outcome is resolved. A violation SHALL fail the run regardless of the step's own expectation, and SHALL name the originated message that caused it.

#### Scenario: The rate window holds across weeks

- **WHEN** a scenario spans many simulated days with signals firing repeatedly
- **THEN** no two nudges reach the same user within one rate window, and a run that violates this fails naming both messages

#### Scenario: Quiet hours hold

- **WHEN** a job executes at an instant inside the user's quiet hours
- **THEN** a nudge originated by that execution fails the run

#### Scenario: An opt-out outlives the run

- **WHEN** a scenario enables nudges, receives one, opts out conversationally, and then declares further silence
- **THEN** no nudge may be originated after the opt-out for the rest of the run, whatever signals fire

#### Scenario: No-retention suppresses nudges

- **WHEN** no-retention mode is enabled and a scenario declares silence across signals that would otherwise fire
- **THEN** no nudge arrives, and one that does fails the run
