## Context

`background-scheduler` ships with zero jobs and a `Scheduler.register(name,
interval_seconds, func)` call this change is the first to use. `advice-memory`
already produces `AdviceRecord` rows with a code-classified `topic` and a lazily-
resolved `outcome`. `advice-longitudinal-signals` already knows how to compute a
period's logging-consistency ratio. `calobot.safety.medical.is_medical_topic` is a
keyword scan usable on any text, not just incoming messages. None of these pieces
currently reach outside a request: nothing in the codebase sends a message to a
chat except in direct response to that chat's own incoming update.

## Goals / Non-Goals

**Goals:**
- A per-user opt-in preference, off by default, changeable by command or by tapping
  a button attached to a nudge.
- A nudge cycle registered as one scheduler job: evaluate every opted-in user,
  compute at most one of three earned signals, respect a rate limit and quiet hours,
  compose a fixed-template message (never LLM-generated), pass it through the
  existing medical/eating-disorder keyword check, and send or stay silent.
- Reuse, not reimplement: the broken-streak and unresolved-suggestion signals are
  read off `advice-longitudinal-signals`'/`advice-memory`'s existing computations.

**Non-Goals:**
- No open-ended natural-language opt-out parsing. See Decisions below for why the
  stop mechanism is a command plus a tappable button, not a text classifier.
- No digest, recap, or timer-only message - every send traces back to one of the
  three named signals.
- No per-user timezone - quiet hours use the same `settings.timezone` every other
  day-boundary computation in this codebase already takes as a parameter.

## Decisions

**The opt-out mechanism is a command plus an inline-keyboard button, never a
freeform text classifier.** The proposal's own framing - "the change most able to do
harm" - is the reason: routing "does this message mean stop" through an LLM adds a
failure mode (a misclassified reply keeps nudges on against the user's clear intent)
to the one interaction that most needs to be unconditionally reliable. A button's
`callback_data` and a `/notifiche_off` command are both deterministic string matches
with no room for misclassification, at the cost of not accepting an arbitrary
sentence as an opt-out - an acceptable trade given what is at stake if it silently
fails the other way.

**Rate limiting is a single `last_nudge_sent_at` column on `User`, not a send-history
table.** The requirement is "at most one nudge per user per N days" - a single
timestamp answers that completely. A full history table would be justified by a
future need to look back at what was sent when, which nothing today requires; adding
it now would be exactly the kind of premature generality the project's conventions
already warn against.

**Signal priority is fixed and only the highest-priority firing signal is sent.**
Goal-reached, then broken-streak, then unresolved-suggestion, in that order - a
concrete, reviewable choice rather than each cycle inventing an order. Goal-reached
is a one-time, celebratory, unambiguous event that would be strange to hold behind a
lower-priority signal; a broken streak is more time-sensitive to say something about
than an unresolved suggestion, which by definition can wait (that's what
"undetermined" already means).

**Broken-streak detection requires prior engagement, not just an empty window.** A
user who logged nothing in the last few days *because they never started* is not
"breaking a streak" - the signal only fires when the same user logged food in the
weeks before the current gap. Reusing `get_entries_in_range` for both windows keeps
this a two-query check with no new aggregation code.

**Goal-reached detection requires the reaching weight entry to be recent.** Without
a recency bound, a user who reached their goal months ago and has stayed there ever
since would be flagged as "just reached it" forever (nothing currently records when a
user was first told). Bounding to a short recent window turns this into a real
"just now" signal at the cost of never re-congratulating someone whose goal weight
entry is older than that window - acceptable, since the moment worth marking is the
transition, not the ongoing state.

**Unresolved-suggestion detection reuses `AdviceRecord.outcome ==
undetermined` directly, filtered to records old enough that `advice-memory`'s own
resolution would have settled them if it could.** This is precisely what "unresolved
after enough time to mean something" means for that data, so no new bookkeeping is
needed beyond an age filter on records `advice-memory` already produces.

**Message content is fixed Italian templates, not an LLM call.** Every other advice
surface in this codebase composes text with an LLM constrained by a system prompt;
this is the one surface where the content constraints (no body commentary, no
"eat less", no failure-framing) are treated as the primary behaviour rather than
limits on it (proposal.md - Risks). A fixed template cannot violate a constraint
prompt engineering only makes less likely. The `is_medical_topic` scan runs anyway,
as defense-in-depth against a future template edit, not because today's templates
are expected to trip it.

**The nudge job needs the `Bot` instance, so it's registered inside `_async_main`
after `bot` is constructed, not inside `Scheduler` itself.** The scheduler module
stays generic (`background-scheduler`'s design already commits to that); this
change's job closure captures `bot` and `settings` the same way any other
`main.py`-level wiring would.

## Risks / Trade-offs

- **A keyword-based `is_medical_topic` scan over a fixed template is a redundant
  safety net, not a real gate** - it will not catch a problem the fixed template
  didn't already avoid by construction. Kept anyway because "route every nudge
  through the existing safety limits" is an explicit proposal requirement, and the
  cost of the check is negligible.
- **The one-command-plus-button opt-out cannot be triggered by an arbitrary sentence
  telling the bot to stop.** Mitigated by making both paths (command, button)
  trivially discoverable: every nudge carries the button, and the command is
  documented in `/help` (proposal.md - Impact: help/welcome text needs updating
  regardless, since it currently describes a reply-only bot).
