## Context

`HELP_TEXT` and `_welcome_message` in `src/calobot/telegram/handlers.py` are the two texts
the `help-and-welcome` spec governs. The help already lists the nudge *commands*; what is
missing is the capability behind them, and the correction capability entirely.

## Goals / Non-Goals

**Goals:** one corrections example, one nudges paragraph, one welcome sentence for counts
and opt-in messages. **Non-Goals:** no behaviour change, no new commands, no restructure
of either text.

## Decisions

### The corrections example uses the amend path, not `/annulla`, as its headline

The spec's discoverability list is about free-form writing; the amend-by-message is the
capability users cannot guess. `/annulla` is mentioned as the delete counterpart in the
same line. Alternative: a separate line per command - rejected, the commands block already
lists `/annulla`.

### The nudges paragraph lives in the prose, and the command lines stay terse

The paragraph carries what the capability is (opt-in, what it may send, how to stop); the
command block keeps its one-line-per-command shape. Duplicating the kinds in the command
line would drift from the paragraph.

### The welcome mentions opt-in messages without a command

First contact happens before onboarding completes, and `/notifiche_on` needs a registered
user; the welcome says the bot *can* write first occasionally and that it is opt-in,
without instructing the user to run anything yet - the help carries the how. Alternative:
showing `/notifiche_on` in the welcome - rejected, it would fail if run immediately, and
"no claim the bot cannot honour" applies.

### Honesty guardrails carried over

The nudges paragraph names only the three signal kinds the spec allows, never frames a
logging gap as failure, and says silence is the default. The welcome's counts line mirrors
the help's exact tracked/not-tracked claim (calories and macronutrients counted; sodium
and sugar not).

## Risks / Trade-offs

- [Text drifts from behaviour again] → the spec scenario "A capability ships without being
  described" plus the content tests added here keep the pair checked.
