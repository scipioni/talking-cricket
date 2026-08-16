## Purpose

Provides an in-process stand-in for the Telegram client so that tests can reach every way a user can act on the bot — typing, tapping a button, tapping an entry control, replying to an earlier message, sending a command — through the same handlers production uses, and can observe exactly what the user would see.

## ADDED Requirements

### Requirement: Every inbound user action is reachable

The transport double SHALL be able to deliver every kind of inbound action the bot handles: a text message, a photo with an optional caption, a command, a tap on an inline option, a tap on an entry control, and a message sent as a reply to an earlier message. Each action SHALL be routed to the same handler that serves it in production, with no branch in production code that exists only for tests.

#### Scenario: Tapping an inline option

- **WHEN** a scenario taps an option offered on an earlier message
- **THEN** the tap is delivered as an inline-option action carrying the same data the real client would send, and is handled by the production answer-callback path

#### Scenario: Tapping an entry control

- **WHEN** a scenario taps the delete control attached to a stored entry's confirmation
- **THEN** the tap is delivered as an entry-control action and the entry is soft-deleted through the production path

#### Scenario: Replying to an earlier message

- **WHEN** a scenario sends a message as a reply to the confirmation of a stored entry
- **THEN** the reply carries the identity of the message it answers, and the correction is targeted at that entry rather than at the most recent one

### Requirement: Faithful message identity

The transport double SHALL assign every outgoing message a unique identifier, expose it to the caller, and accept it back as the target of a reply. Identifiers SHALL behave as the values production stores when linking a confirmation message to the entry it confirms.

#### Scenario: Confirmation message is addressable

- **WHEN** the bot stores an entry and sends its confirmation
- **THEN** the identifier recorded against that entry is the identifier of the message that was sent, and replying to that identifier addresses that entry

#### Scenario: Identifiers are distinct

- **WHEN** several messages are sent during a scenario
- **THEN** no two carry the same identifier, and an identifier remains valid as a reply target for the rest of the scenario

### Requirement: Options are addressed by their visible label

The transport double SHALL expose the options attached to each outgoing message by the label a user would read, and SHALL translate a tap on a label into the underlying action data. A scenario SHALL NOT need to know that data, and tapping a label that is not currently offered SHALL be reported as a scenario error rather than silently delivered.

#### Scenario: Tap by label

- **WHEN** a scenario taps the label "medio (~120g)" offered on the most recent question
- **THEN** the action delivered is the one the real client would send for that label

#### Scenario: Tap on a label that was never offered

- **WHEN** a scenario taps a label that appears on no message in the transcript
- **THEN** the run reports a scenario error and does not deliver an action

#### Scenario: Tap on a superseded keyboard

- **WHEN** a scenario taps a label from an earlier message whose options are no longer the current question
- **THEN** the action is delivered as the real client would deliver it, so that the bot's own handling of a stale tap is what is being tested

### Requirement: Observable transcript

The transport double SHALL record every outgoing message in order, with its text, its identifier, the options currently attached to it, and whether it carried an image. When the bot later changes the controls attached to an already-sent message, the transcript SHALL reflect the change against that message.

#### Scenario: Controls replaced after sending

- **WHEN** the bot sends a confirmation and then attaches entry controls to it
- **THEN** the transcript shows that message carrying the entry controls, not the controls it was sent with

#### Scenario: Chart replies

- **WHEN** the bot replies with a chart
- **THEN** the transcript records that the message carried an image and preserves its caption, without requiring the image to be decoded

### Requirement: Declared fidelity boundary

The transport double SHALL emulate a single private chat with a single user, delivering actions one at a time and in the order a scenario issues them. It SHALL NOT emulate delivery failures, rate limiting, message reordering, or concurrent updates. Behaviour that depends on any of those SHALL NOT be asserted through this capability.

#### Scenario: Out-of-scope behaviour is not silently faked

- **WHEN** a scenario would require a delivery failure or a rate limit to be meaningful
- **THEN** the capability provides no way to express it, rather than providing an approximation that would make a passing run misleading
