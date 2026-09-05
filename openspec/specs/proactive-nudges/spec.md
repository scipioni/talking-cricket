# proactive-nudges Specification

## Purpose
Lets the bot send a small number of unprompted messages to users who have opted in,
only when a computed signal or an unresolved suggestion warrants one, within strict
rate, timing, content and safety limits, so a user can be told something worth
knowing without the bot ever becoming a source of unwanted messages about their
eating or weight.

## Requirements

### Requirement: Nudges are off until a user opts in

The system SHALL default every user to no unprompted messages. A user SHALL only
receive a nudge after explicitly enabling it, and SHALL be able to enable or disable
it at any time by command, by tapping the stop control attached to a nudge, or by
stating the preference in free-form language.

#### Scenario: Default state is off

- **WHEN** a user has never changed their nudge preference
- **THEN** the system never sends them an unprompted message

#### Scenario: User enables nudges

- **WHEN** a user runs the command to enable nudges
- **THEN** the preference is stored as enabled, and the system confirms the change

#### Scenario: User enables nudges conversationally

- **WHEN** a user writes that they want the bot's occasional messages
- **THEN** the preference is stored as enabled, and the system confirms the change in
  one reply, exactly as the command does

#### Scenario: User disables nudges by command

- **WHEN** a user runs the command to disable nudges
- **THEN** the preference is stored as disabled immediately, and no further nudge is
  sent until re-enabled

#### Scenario: User disables nudges conversationally

- **WHEN** a user writes that they no longer want the bot's occasional messages
- **THEN** the preference is stored as disabled immediately, honoured for every future
  cycle, and the system confirms the change in one reply

#### Scenario: The preference is already in the asked-for state

- **WHEN** a user states a nudge preference the user already has
- **THEN** the system confirms the current state without presenting the statement as a
  change

#### Scenario: User disables nudges from a nudge itself

- **WHEN** a user taps the stop control included with a nudge
- **THEN** the preference is stored as disabled immediately, honoured for every
  future cycle, and the system confirms the change

### Requirement: A nudge is sent only on an earned signal

The system SHALL send a nudge only when a specific, computed condition holds for
that user at that time: a broken logging streak, a newly reached weight goal, or an
actionable suggestion recorded for the user that remains unresolved. The system
SHALL NOT send a nudge on a fixed schedule alone, and a cycle that finds no such
condition for a user SHALL send nothing to them.

#### Scenario: No signal fires

- **WHEN** a nudge cycle runs for an opted-in user and none of the earned conditions
  hold
- **THEN** no message is sent to that user this cycle

#### Scenario: A broken logging streak

- **WHEN** an opted-in user who was logging consistently has logged nothing for
  several consecutive days
- **THEN** the system may send a nudge referencing the gap, without framing it as a
  failure

#### Scenario: A weight goal newly reached

- **WHEN** an opted-in user's most recently logged weight newly reaches their stated
  goal
- **THEN** the system may send a nudge acknowledging the goal was reached

#### Scenario: An unresolved recorded suggestion

- **WHEN** an opted-in user has an actionable suggestion recorded for them whose
  outcome is still undetermined after enough time has passed to ask about it
- **THEN** the system may send a nudge referencing that suggestion

### Requirement: Nudges are rate-limited and time-boxed

The system SHALL send at most one nudge to a given user within a fixed minimum
number of days, regardless of how many earned signals fire in that window. The
system SHALL NOT send a nudge during a configured quiet-hours window in the
timezone the system already uses for day-boundary logic.

#### Scenario: Multiple signals fire in the same window

- **WHEN** more than one earned signal holds for a user within the minimum interval
  since their last nudge
- **THEN** at most one nudge is sent, not one per signal

#### Scenario: Rate limit not yet elapsed

- **WHEN** a user received a nudge more recently than the minimum interval
- **THEN** no new nudge is sent to them even if a new signal fires

#### Scenario: Cycle runs during quiet hours

- **WHEN** a nudge cycle runs during the configured quiet-hours window
- **THEN** no nudge is sent during that window, regardless of any signal

### Requirement: Nudge content is constrained

A nudge SHALL NOT comment on the user's body. A nudge SHALL NOT frame a gap in
logging as a failure. A nudge SHALL NOT encourage eating less. A nudge MAY
reference the user's logged behaviour and advice already given to them.

#### Scenario: Logging-gap nudge stays non-judgemental

- **WHEN** the system composes a nudge about a broken logging streak
- **THEN** the message does not characterize the gap as a failure or shortcoming

#### Scenario: No body commentary

- **WHEN** the system composes any nudge
- **THEN** the message does not comment on the user's body or appearance

#### Scenario: No push toward eating less

- **WHEN** the system composes any nudge
- **THEN** the message does not suggest or imply eating less

### Requirement: Nudges pass through existing safety limits

Before a nudge is sent, the system SHALL apply the same safety checks that govern a
reply the bot originates in conversation. A composed nudge that would trip a safety
check SHALL NOT be sent.

#### Scenario: A composed nudge trips a safety check

- **WHEN** a composed nudge's text matches a topic the existing safety checks
  refuse
- **THEN** that nudge is not sent

### Requirement: No-retention mode suppresses nudges entirely

While a chat is in no-retention mode, the system SHALL NOT schedule or send a nudge
for it, consistent with every other write and outbound effect no-retention mode
already suppresses.

#### Scenario: No-retention mode is active

- **WHEN** a nudge cycle runs for a chat currently in no-retention mode
- **THEN** no nudge is evaluated or sent for that chat this cycle

### Requirement: Nudge evaluation runs as a scheduled job

The system SHALL register its nudge evaluation cycle as a job on the background
scheduler, and SHALL own only what the cycle does and whether a message may be
sent — not the mechanics of running something periodically.

#### Scenario: The cycle runs on schedule

- **WHEN** the scheduler's registered interval for the nudge job elapses
- **THEN** the nudge cycle evaluates every opted-in user and sends at most the
  nudges the other requirements in this capability allow
