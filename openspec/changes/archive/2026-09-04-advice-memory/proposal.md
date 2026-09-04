## Why

The bot gives advice and immediately forgets it. The dietician review ends with a single
actionable tip; `build_daily_advice` produces rest-of-day advice on every daily report;
the advice agent suggests meals. None of it is recorded anywhere. The agent's only
access to its own past is `_get_recent_history_context`, which scrapes the last six
lines out of the telemetry buffer for pronoun resolution — a coreference crutch, not
memory, and sourced from a buffer meant for observing the system rather than for the
system to observe itself with.

The consequence is that the bot cannot ask "hai provato?", cannot notice that the user
did, cannot stop repeating a suggestion that was already rejected, and cannot escalate
one that keeps being ignored. A nutritionist who does not remember the last session is a
lookup service. Remembering across time is what makes the difference, and it is the one
missing piece that the rest of the depth ladder rests on.

## What Changes

- Add a durable record of advice the bot has given: what was suggested, when, in
  response to which situation, and through which surface (dietician review, daily
  advice, or an advice-agent answer). Written by the code that emits the advice, not by
  the model reporting on itself.
- Record an outcome for each piece of advice, determined deterministically where it can
  be: a suggestion about meal timing is checked against subsequently logged entries, one
  about logging consistency against subsequent logging. Where an outcome cannot be
  determined from logged data, it stays explicitly undetermined rather than guessed.
- Give the advice agent a read-only tool over that record, so an answer can reference
  what was already suggested and whether it was acted on.
- Suppress repetition: an actionable tip that was given recently and neither followed
  nor rejected is not re-issued verbatim.
- Honour the existing no-retention mode (`/memory_off`): while it is on, nothing is
  recorded, exactly as entries are not.
- Include advice records in `/cancellami`, the one intentional hard-delete.

**Non-goals:** no change to the wording or quality of the advice itself; no
model-written summary of the user ("profiling"); no unprompted message — that is
`proactive-nudges`.

## Capabilities

### New Capabilities

- `advice-memory`: records the advice the bot has given to a user and, where logged data
  can settle it, whether that advice was subsequently followed, so later advice can
  build on earlier advice instead of repeating it.

### Modified Capabilities

- `advice-agent`: gains requirements that a suggestion it makes is recorded, that it may
  read prior advice when answering, and that it does not re-issue a recent unresolved
  tip verbatim.
- `dietician-reviews`: its single actionable recommendation is recorded like any other
  advice, so the tip stops being fire-and-forget.
- `user-profile`: `/cancellami` removes advice records along with everything else.

## Impact

- **New table and an Alembic migration** (`task migration -- "..."`) — the first schema
  change in this line of work. Soft-delete conventions apply to it as they do to
  entries.
- `src/calobot/reporting/dietician.py` — the review's tip and `build_daily_advice`'s
  output become recorded events.
- `src/calobot/advice/` — a write on the advice path, plus one read-only tool. Note this
  is the first thing on the advice path that writes anything: the `advice-agent`
  requirement "The agent's data access is read-only" governs the *model's tools*, and
  that boundary must stay intact — the tool set stays read-only while the surrounding
  code records what was said.
- `src/calobot/persistence/` — model, repository accessors, `/cancellami` coverage.
- No new dependency.

## Dependencies

Reads better after `advice-longitudinal-signals`, which supplies the deterministic
signals an outcome check compares against, but does not strictly require it.
