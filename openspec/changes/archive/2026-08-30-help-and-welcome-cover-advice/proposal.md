## Why

The `/help` text and the welcome message are the only two places the bot describes
itself, and no spec governs either. Both predate the advice agent: it shipped
2026-08-17, meal suggestions followed on 2026-08-23, and neither message mentions that
you can ask the bot anything at all. A user's only route to discovering the capability
is guessing that a question might work.

The drift is not a one-off. These strings have fallen behind twice now — once for the
advice agent, once for meal suggestions — because nothing ties them to the capabilities
they describe. Making them spec-governed means the next capability that ships has a
requirement telling it to say so.

## What Changes

- Cover both messages with a capability spec: what the welcome message must establish
  for a first-time user, and what the help text must let an existing user discover.
- Require that every conversational capability a user can invoke by writing to the bot
  is discoverable from the help text — logging food, activity and weight; asking about
  their own data; asking for a meal suggestion; sending photos; correcting the profile;
  requesting reports.
- Require the welcome message to keep its experimental / not-medical-advice disclaimer,
  which today only a test enforces.
- Require the help text to state what the bot does **not** track, so a user learns the
  macronutrient limit from the documentation rather than by hitting the refusal.
- Update both strings accordingly. The advice-agent and meal-suggestion lines are
  already in place; this change adds the untracked-quantities note and puts the whole
  thing under spec.

**Non-goals:** no change to any bot behaviour, no new command, no change to what the
advice agent can do. This is about what the bot says it can do.

## Capabilities

### New Capabilities

- `help-and-welcome`: the two self-describing messages — the first-contact welcome and
  the `/help` reference — and the requirement that they stay in step with the
  capabilities a user can actually reach by writing to the bot.

### Modified Capabilities

None. No existing capability's behaviour changes.

## Impact

- `src/calobot/telegram/handlers.py` — `HELP_TEXT` and `_welcome_message`.
- `tests/test_welcome_message.py` — extended to cover the new requirements; the
  existing disclaimer assertions become spec-backed rather than incidental.
- No database schema change, no migration, no new dependency, no LLM call.
