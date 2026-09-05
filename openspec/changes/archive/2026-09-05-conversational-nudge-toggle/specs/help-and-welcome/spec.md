## MODIFIED Requirements

### Requirement: Every conversational capability is discoverable from the help text

The help text SHALL let a user discover each thing they can do by writing to the bot in
free-form language, with at least one concrete example of each: logging food, logging
physical activity, logging weight, requesting a report, asking a question about their own
logged data, asking for a meal or recipe suggestion, sending a photo, correcting a profile
field, and correcting an entry that was already stored. It SHALL also list the commands the
bot responds to. It SHALL describe the proactive-nudge capability: that the bot can write
first when the user has opted in, the kinds of messages it may originate, that nudges are
off by default, and that they are turned off by one reply, by the dedicated command, or by
tapping the stop control on a nudge itself.

#### Scenario: A user asks what the bot can do

- **WHEN** a user requests the help text
- **THEN** it presents both the available commands and a concrete written example for
  each conversational capability, including asking questions about their own data and
  asking for a meal suggestion

#### Scenario: A capability ships without being described

- **WHEN** a capability a user can reach by writing to the bot is added or changed
- **THEN** the help text is updated in the same change, so no reachable capability is
  left undiscoverable

#### Scenario: A user wants to fix a stored entry

- **WHEN** a user reads the help text
- **THEN** it shows that writing the correction after storing amends the entry, and that
  a command exists to delete the most recent one

#### Scenario: A user wonders whether the bot will message them

- **WHEN** a user reads the help text
- **THEN** it states that the bot sends occasional proactive messages only after the user
  opts in, names the kinds of message it may send, and shows that they can be turned off
  in words as well as by command
