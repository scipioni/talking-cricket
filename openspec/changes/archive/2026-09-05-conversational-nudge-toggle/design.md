## Context

The intent taxonomy is a closed Literal in `ingestion/schemas.py`, one line in the
classifier prompt per intent, one tiny extraction schema per intent, and one dispatch
branch in `IngestionPipeline.handle` (see `report` for the non-storing pattern). Nudge
state is `User.nudges_enabled`, written by the `/notifiche_on`/`/notifiche_off` handlers
and the stop-callback handler today.

## Goals / Non-Goals

**Goals:** stating the preference in words does what the commands do. **Non-Goals:** no
new commands, no change to the cycle's gates, no LLM-narrated confirmation.

## Decisions

### A dedicated `nudges` intent, not a profile field

The profile-edit flow parses and confirms *field values* (dates, numbers, enums) with a
draft and a confirmation round-trip - machinery a reversible boolean toggle does not
need, and the preference is owned by `proactive-nudges`, not by the profile capability.
A one-field extraction (`enable`/`disable`) with a deterministic reply matches how the
codebase splits intents: "each intent gets its own tiny schema".

### One reply, no confirmation round-trip

Storing an entry asks before writing; setting a profile field confirms first. A nudge
toggle is the opposite of dangerous: it is instantly reversible by saying the opposite,
so the pipeline applies and confirms in one deterministic message - the same text the
commands already send. Asking "confermi?" for a toggle would be the bot refusing to take
yes for an answer.

### Idempotence says the truth, not "done"

When the stated state equals the current one, the reply says the nudges are already
on/off rather than claiming a change happened - the same honesty the false-confirmation
invariant demands of entries, applied to a preference.

### Mixed messages keep the existing rule

A nudge statement alongside a loggable intent ("voglio le notifiche e ho mangiato una
mela") routes by the existing dominant-intent rule: the food is logged, the nudge part
is silently dropped - the same outcome as a report request in a mix today. Narrowing
`ignored_text` to carry it would invent a second processing path for no real gain.

## Risks / Trade-offs

- [Classifier confuses "notifiche" statements with advice questions] → the prompt line
  carries concrete examples for both directions; the e2e tests pin them.
- [The closed intent list drifts between prompt, schema and spec] → all three change in
  this one commit; the classifier prompt is the only place intents are named in prose.
