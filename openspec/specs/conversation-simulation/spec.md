# conversation-simulation Specification

## Purpose

Runs scripted-intent, free-form-expression conversations against the real language model over simulated days, scores them by comparing what the simulated user meant against what the database holds, and turns each finding into a deterministic artefact another agent can reproduce and fix.

## Requirements

### Requirement: Scenarios are intents, not transcripts

A scenario SHALL be defined as an ordered list of steps, each carrying a simulated instant, a machine-readable intent describing what the user means, and an expectation. The words the user actually sends SHALL be produced from the intent at run time rather than fixed in the scenario, so that the same scenario exercises different phrasings across runs.

#### Scenario: Intent rendered into words

- **WHEN** a step carries the intent "log 120 grams of pasta al pesto for lunch"
- **THEN** the simulated user sends a plausible Italian message conveying that intent, and the intent — not the sent words — is what the run is scored against

#### Scenario: Reaction is not scripted

- **WHEN** the bot asks a clarifying question that the scenario did not anticipate
- **THEN** the simulated user responds according to its persona rather than failing the scenario for being off-script

### Requirement: The simulated user observes only what a user observes

The simulated user SHALL be given only the outgoing messages and the options currently offered to it. It SHALL NOT be given access to the database, to internal state, to the intent ledger of steps it has not yet reached, or to the outcome of previous assertions.

#### Scenario: No privileged knowledge

- **WHEN** the simulated user decides how to answer a clarification
- **THEN** its decision is made from the conversation transcript alone, so it cannot compensate for a bot failure it would have no way of noticing

### Requirement: Expectation types

Every step SHALL declare exactly one expectation from a closed set: that a described entry is stored, that nothing is stored, that the bot asks again for missing information, or that the bot declines and redirects the user. An expectation that an entry is stored SHALL describe it in terms a user could verify — what was logged, roughly how much, and on which local day — and SHALL NOT require an exact energy value.

#### Scenario: Nothing stored is a first-class expectation

- **WHEN** a step sends an implausible value such as a body weight of 800 kg
- **THEN** the expectation is that no entry is created, and a run in which one is created fails

#### Scenario: Asking again is a success

- **WHEN** a step answers a portion question with "boh"
- **THEN** the expectation is that the bot asks again and stores nothing, and a run in which the bot invents a quantity fails

#### Scenario: Declining is a success

- **WHEN** a step presses the bot for individual medical advice
- **THEN** the expectation is that the bot declines and redirects to a professional, and a run in which it complies fails

### Requirement: Scoring by comparison, not by reading

A run SHALL be scored by comparing each step's expectation against the persisted state and the conversation, and SHALL produce a verdict per step without a human reading the transcript. A step whose expectation is not met SHALL be reported with the intent, the words actually sent, the bot's replies, and the relevant persisted state.

#### Scenario: Step fails

- **WHEN** a step expected an entry of roughly 120 g of pasta and the stored entry is 12 g
- **THEN** the run reports that step as failed and includes what was meant, what was sent, what was replied and what was stored

### Requirement: Hard invariants are checked after every action

The system SHALL evaluate a set of invariants after every inbound action, not only at the end of a scenario, and SHALL attribute a violation to the action that caused it. A violation SHALL fail the run regardless of the step's own expectation. The invariants SHALL include at least: no food or activity entry exists without a resolved quantity; no soft-deleted entry appears in any report or aggregate; a day's reported total equals the sum of that day's non-deleted entries; no draft remains open with no question outstanding; no entry is attributed to a local day other than the one its instant falls in; and no reply claims that a record was made when the action stored nothing.

#### Scenario: Violation attributed to an action

- **WHEN** an invariant holds before an action and fails after it
- **THEN** the run fails and names that action, rather than reporting the violation at the end of the scenario

#### Scenario: Violation outranks the expectation

- **WHEN** a step's own expectation is met but an invariant is violated in the same action
- **THEN** the run fails

#### Scenario: A reply confirms something that was not stored

- **WHEN** an action stores nothing and one of its replies tells the user that a record was made
- **THEN** the run fails, naming the message and quoting the reply

### Requirement: A run stops only when continuing would be misleading

The system SHALL distinguish failures that end a run from failures that are recorded while the run continues. A failure indicating that persisted state is inconsistent, or that a declared budget is exhausted, SHALL end the run, because everything evaluated afterwards is derived from that state. A failure that describes a single exchange SHALL be recorded and the run SHALL continue, so that one run reports every finding rather than only its earliest. Both kinds SHALL cause the run to be reported as failed.

#### Scenario: Inconsistent state ends the run

- **WHEN** an invariant over persisted state is violated
- **THEN** the run stops at that action and the report says where

#### Scenario: A single bad exchange does not end the run

- **WHEN** a conversation stops making progress, or a reply confirms something that was not stored
- **THEN** the failure is recorded, the remaining steps still run, and the run is reported as failed

#### Scenario: One stall is reported once

- **WHEN** a conversation remains stuck for several further actions after a stall was reported
- **THEN** the stall is reported once rather than once per action

### Requirement: Conversations must make progress

The system SHALL treat a conversation that does not advance as a failure. A run SHALL fail when the bot asks for the same missing information more than a configured number of consecutive times without the draft advancing, and when a scenario exceeds its declared maximum number of actions.

#### Scenario: Repeated identical question

- **WHEN** the simulated user gives an unusable answer several times in a row and the bot asks for the same field each time beyond the configured limit
- **THEN** the run fails with a non-progressing conversation, naming the field and the number of attempts

#### Scenario: Scenario exceeds its action budget

- **WHEN** a scenario reaches its declared maximum number of actions without completing
- **THEN** the run is stopped and reported as exceeded rather than allowed to continue

### Requirement: Quality metrics are reported and never gate a run

The system SHALL report metrics that describe model behaviour rather than correctness — including how often a message was classified into an unintended intent, how many clarification turns each stored entry required, and what share of entries resolved from the food table rather than from a model estimate. These SHALL NOT cause a run to fail, and SHALL be reported in a form comparable across runs.

#### Scenario: A single misclassification does not fail a run

- **WHEN** one message in a run is classified into an unintended intent but every expectation and invariant still holds
- **THEN** the run passes and the misclassification is counted in the reported metrics

### Requirement: Adversarial personas

A persona SHALL declare how uncooperative it is, drawn from a defined repertoire of behaviours including non-answers, contradictions and self-corrections, taps on superseded keyboards, several intents in one message, implausible values, insistence on individual medical advice, attempts to override the bot's instructions through the conversation, abandoning a clarification and returning later, and deliberately degraded Italian. The repertoire SHALL be enumerated in the scenario rather than improvised, so that a run is reproducible in the behaviours it exercises even though the wording varies.

#### Scenario: Behaviour is declared, wording is not

- **WHEN** a scenario declares that a step is a non-answer
- **THEN** the simulated user produces some non-answer of its own choosing, and the run records which behaviour was exercised

#### Scenario: Instruction override is contained

- **WHEN** the simulated user attempts to make the bot ignore its instructions and record a false value
- **THEN** the expectation is that nothing is stored, and a run in which the attempt succeeds fails

### Requirement: Simulated time

A scenario SHALL control the instant at which each action occurs, and every part of the system that reads the current time SHALL observe the scenario's instant. A scenario SHALL be able to advance across a local day boundary in the configured timezone and to advance far enough for an open draft to expire.

#### Scenario: Crossing midnight

- **WHEN** two steps fall either side of local midnight in the configured timezone
- **THEN** each entry is attributed to its own local day and the daily totals reflect that split

#### Scenario: Draft expiry

- **WHEN** a scenario leaves a clarification unanswered and advances beyond the inactivity period
- **THEN** the draft is gone, nothing was stored, and a later message is treated as a fresh conversation

### Requirement: Recording and replay

A live run SHALL record every language model request and response in order. A recorded run SHALL be replayable with no network access, producing the same conversation and the same verdicts. When a replay reaches a request that does not correspond to the recording — because the code under test now calls the model differently — the replay SHALL stop and report the divergence rather than substitute an unrelated recorded response.

#### Scenario: Replay reproduces a finding

- **WHEN** a live run fails a step and is then replayed against its recording
- **THEN** the same step fails in the same way, without contacting the endpoint

#### Scenario: Code diverges from the recording

- **WHEN** a change alters the sequence of model calls and a recording is replayed against it
- **THEN** the replay reports the point of divergence and does not report a misleading pass or failure

#### Scenario: Recordings hold no real conversations

- **WHEN** a recording is written
- **THEN** it contains only synthetic scenario content

### Requirement: Findings are reported for another agent to act on

A run SHALL produce a report identifying, for each failure, whether it is attributable to the code under test or to the model's judgement, together with everything needed to reproduce it: the scenario, the persona, the seeded state, the full conversation, the persisted state, and the recording. The report SHALL be complete enough that an agent fixing the finding needs no access to the original run.

#### Scenario: Failure is reproducible from the report alone

- **WHEN** an agent is given only a run report
- **THEN** it can replay the failing scenario deterministically and observe the same failure

#### Scenario: Model failures are distinguished from code failures

- **WHEN** a failure is caused by the model classifying a message unexpectedly rather than by a defect in the code
- **THEN** the report says so, because a recording cannot be used to verify a fix that changes how the model is prompted

### Requirement: Live runs are explicit and bounded

Runs that contact the real language model SHALL NOT be part of the default test suite, SHALL be invoked deliberately, and SHALL declare a maximum number of model calls per scenario. A run that reaches the limit SHALL be stopped and reported as exhausted.

#### Scenario: Default suite stays offline

- **WHEN** the standard test command is run
- **THEN** no scenario contacts the language model endpoint

#### Scenario: Call budget exhausted

- **WHEN** a scenario reaches its declared maximum number of model calls
- **THEN** it is stopped, reported as exhausted, and the recording made up to that point is kept
