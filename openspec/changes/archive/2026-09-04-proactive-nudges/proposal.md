## Why

Every message the bot has ever sent is a reply. It cannot notice that a user who logged
daily for three weeks has logged nothing for four days, that a goal was reached, or that
a suggestion it made has been quietly ignored twice — or rather, it can compute all of
that, and has no way to say it. With `advice-longitudinal-signals` supplying what
changed and `advice-memory` supplying what was already suggested, the bot has something
worth saying unprompted for the first time; this change gives it permission to say it,
under tight limits.

The limits are the substance of this proposal, not a caveat on it. An unprompted message
about someone's eating and weight is a different act from answering a question about it.

## What Changes

- Add a per-user nudge setting, **off by default**, turned on and off conversationally
  and by command. No user receives an unprompted message without having enabled it.
- Send only on an earned signal, never on a timer: a broken logging streak, a goal
  reached, a recorded suggestion left unresolved. When no signal fires, the bot stays
  silent — a nudge cycle that produces nothing sends nothing.
- Rate-limit hard: at most one nudge per user per N days regardless of how many signals
  fire, and a quiet-hours window in the user's timezone (which the day-boundary logic
  already takes as a parameter).
- Make every nudge trivially stoppable: one reply turns it off, and turning it off is
  honoured immediately and permanently until re-enabled.
- Route every nudge through the existing safety limits before sending. The medical
  refusal path and the eating-disorder boundary in `calobot.safety` apply to text the
  bot originates exactly as they apply to text it replies with.
- Constrain content: a nudge may reference logged behaviour and prior advice. It SHALL
  NOT comment on the user's body, SHALL NOT frame a gap in logging as a failure, and
  SHALL NOT nudge toward eating less. Silence is always an acceptable outcome.
- Respect no-retention mode: while `/memory_off` is on, no nudge is scheduled or sent.
- Register the nudge cycle as a job on the scheduler that `background-scheduler`
  introduces. This change owns *what the cycle does and whether a message may be sent*;
  it owns none of the machinery for running something periodically.

**Non-goals:** no scheduled digest or recap on a fixed cadence; no notification of
anything a report would tell them anyway; no re-engagement messaging aimed at users who
have stopped using the bot.

## Capabilities

### New Capabilities

- `proactive-nudges`: lets the bot send a small number of unprompted messages to users
  who have opted in, only when a computed signal or an unresolved suggestion warrants
  one, within strict rate, timing, content and safety limits.

### Modified Capabilities

- `user-profile`: gains the nudge preference, its default-off state, and its inclusion
  in the profile view and in `/cancellami`.
- `advice-memory`: an unresolved recorded suggestion becomes one of the signals that can
  warrant a nudge.

## Impact

- `src/calobot/nudges/` (new module) — the cycle: gather candidate signals, apply the
  limits, decide to send or stay silent. Registered as one job on the scheduler.
- `src/calobot/telegram/` — sending to a chat the bot did not just hear from, plus the
  opt-out reply path; also the help and welcome text, which currently describe a
  reply-only bot.
- `src/calobot/safety/` — the existing refusal checks applied to originated text.
- **Schema change and Alembic migration** for the preference and the per-user send
  history the rate limit needs.
- No scheduling machinery and no `main.py` change: `background-scheduler` supplies both,
  including the multi-instance question that a timer-driven sender would otherwise have
  to answer for itself.

## Risks

- **This is the change most able to do harm.** A nutrition bot messaging someone
  unprompted about eating and weight sits next to the eating-disorder boundary the
  project already refuses to cross on request. The content constraints above are
  requirements, not guidance, and the specs phase should treat them as the primary
  behaviour rather than as limits on it.
- Notification fatigue turns a helpful bot into an unwanted one, and the cost is
  asymmetric: a missed nudge costs nothing, an unwanted one costs the user's trust.
  Every default in this proposal is set accordingly.

## Dependencies

Requires `background-scheduler` (supplies the periodic execution and the
multi-instance answer), `advice-longitudinal-signals` (supplies the signals) and
`advice-memory` (supplies unresolved-suggestion state and the send history's natural
home). Building this first would mean inventing all three, and would produce a bot that
speaks unprompted without having anything specific to say.
