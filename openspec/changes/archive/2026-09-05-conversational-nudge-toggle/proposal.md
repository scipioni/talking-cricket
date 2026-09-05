## Why

Nudges can only be turned on and off by exact commands or the stop button on a nudge
itself. Every other preference the bot honours can be stated in words ("ora il mio peso
obiettivo è 74kg"), and a user who just read "basta notifiche" into the chat gets a
conversational reply that changes nothing - the preference is real, the words for it are
missing. The original nudges proposal promised "turned on and off conversationally and by
command"; this delivers the conversational half.

## What Changes

- Add a `nudges` intent to the message classifier: a statement that sets the nudge
  preference ("voglio ricevere le notifiche", "basta notifiche") is classified as `nudges`
  and extracted with its own tiny schema (enable or disable).
- The pipeline applies the stated state to the user's nudge preference directly and
  confirms in one deterministic reply - no draft, no confirmation round-trip: the toggle
  is reversible in one message, unlike a profile field or a stored entry.
- The help text mentions the free-form way alongside the commands.
- Commands and the nudge stop button keep working exactly as before.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `message-ingestion`: the closed intent list gains `nudges`, with scenarios for an
  enable statement and a disable statement.
- `proactive-nudges`: opt-in and opt-out may happen conversationally, not only by
  command or the stop control.
- `help-and-welcome`: the nudge description in the help text mentions the free-form way.

## Impact

- `src/calobot/ingestion/schemas.py`, `classifier.py`, `extractors.py`, `pipeline.py` -
  one Literal entry, one prompt line, one extraction function, one handler branch.
- `src/calobot/telegram/handlers.py` - one help-text sentence.
- Tests: pipeline behaviour for both directions and idempotence, help content assertion.
