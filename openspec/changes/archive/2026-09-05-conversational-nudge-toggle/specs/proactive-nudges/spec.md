## MODIFIED Requirements

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

#### Scenario: User disables nudges from a nudge itself

- **WHEN** a user taps the stop control included with a nudge
- **THEN** the preference is stored as disabled immediately, honoured for every
  future cycle, and the system confirms the change

#### Scenario: The preference is already in the asked-for state

- **WHEN** a user states a nudge preference the user already has
- **THEN** the system confirms the current state without presenting the statement as a
  change
