## Why

Two capabilities a user can reach from the chat are not discoverable from the help text:
correcting an entry that was already stored by simply writing the correction (`entry-correction`
is implemented and specified but undocumented), and the proactive-nudge capability itself -
the help lists `/notifiche_on` and `/notifiche_off` as bare commands without saying what the
bot may write about or that it is off by default. The welcome message, the user's very first
impression, mentions neither macronutrients nor that the bot can write first. The
`help-and-welcome` spec's own rule is that a capability ships with its description; these
descriptions are overdue.

## What Changes

- The help text gains a corrections line: writing the correction right after storing (e.g.
  "no, erano 200g") amends the most recent entry, and `/annulla` deletes it outright.
- The help text describes the nudge capability in one place: what kinds of messages the bot
  may originate (a pause in logging, a goal reached, an advice left unapplied), that they are
  off by default, and that one reply or `/notifiche_off` turns them off.
- The welcome message states that calories and macronutrients are tracked (sodium and sugar
  are not), and that the bot can send occasional messages once the user opts in - without
  promising anything the bot does not do, and without touching the disclaimer or the lead
  into profile setup.
- No behaviour changes: message content only.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `help-and-welcome`: the discoverability requirement's list is extended to stored-entry
  corrections and to the nudge capability (opt-in, what the bot may originate, how to stop);
  the welcome requirement gains what it must mention about tracking and opt-in messages.

## Impact

- `src/calobot/telegram/handlers.py` - `HELP_TEXT` and `_welcome_message` content only.
- `tests/test_help_command.py` - content assertions for the new lines.
- No schema, no `src/` behaviour change beyond message text.
