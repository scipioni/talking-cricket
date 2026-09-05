# help-and-welcome Specification

## Purpose

Governs the two messages in which the bot describes itself — the welcome a user meets on
first contact and the `/help` reference they can ask for at any time — so that what the
bot says it can do stays in step with what it can actually do.

## Requirements

### Requirement: The welcome message orients a first-time user

On first contact the system SHALL send a message that names the bot, states that it
tracks food, weight and physical activity, and shows concrete examples of writing to it
in free-form language. The message SHALL state which quantities are counted - calories
and macronutrients - and that others, in particular sodium and sugar, are not. It SHALL
say that the bot can also write first, occasionally and only after the user opts in. The
message SHALL state that the bot is experimental software and does not replace medical
advice, and SHALL direct the user to a professional for health goals. It SHALL end by
leading into profile setup, since a calorie budget cannot be computed without it.

#### Scenario: A new user makes first contact

- **WHEN** a user starts the bot for the first time
- **THEN** they receive a message naming the bot, describing what it tracks, showing
  examples of how to write to it, and leading into profile setup

#### Scenario: The disclaimer is present

- **WHEN** the welcome message is composed
- **THEN** it states that the software is experimental and is not a substitute for
  medical advice

#### Scenario: The welcome is honest about counts and proactive messages

- **WHEN** the welcome message is composed
- **THEN** it names calories and macronutrients as counted, sodium and sugar as not, and
  describes the bot's own messages as occasional and opt-in

### Requirement: Every conversational capability is discoverable from the help text

The help text SHALL let a user discover each thing they can do by writing to the bot in
free-form language, with at least one concrete example of each: logging food, logging
physical activity, logging weight, requesting a report, asking a question about their own
logged data, asking for a meal or recipe suggestion, sending a photo, correcting a profile
field, and correcting an entry that was already stored. It SHALL also list the commands the
bot responds to. It SHALL describe the proactive-nudge capability: that the bot can write
first when the user has opted in, the kinds of messages it may originate, that nudges are
off by default, and that one reply or the dedicated command turns them off.

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
  opts in, names the kinds of message it may send, and shows how to turn them off

### Requirement: The help text states what the bot does not track

The help text SHALL name at least the quantities a user is most likely to assume are
tracked and are not — in particular sodium and sugar — so that the limit is learned from
the documentation rather than from being refused mid-conversation. Where the bot does
track a quantity (calories and, as of this requirement's update, macronutrients), the help
text SHALL say so rather than disclaiming it.

#### Scenario: A user wonders whether macronutrients are tracked

- **WHEN** a user reads the help text
- **THEN** it states that the bot tracks calories and macronutrients, and does not track
  sodium or sugar

### Requirement: Self-description makes no claim the bot cannot honour

Neither message SHALL describe a capability that is not implemented, and neither SHALL
promise medical, clinical or diagnostic guidance. An example shown to the user SHALL be
one the bot would actually handle as described.

#### Scenario: An example is shown for an unimplemented capability

- **WHEN** either message would show an example of something the bot cannot do
- **THEN** that example is not presented to the user

#### Scenario: No clinical promise is made

- **WHEN** either message describes what the bot is for
- **THEN** it does not offer medical, clinical or diagnostic guidance
