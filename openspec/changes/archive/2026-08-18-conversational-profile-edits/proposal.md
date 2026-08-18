# Conversational profile edits

## Why

The onboarding conversation is the only moment a profile field is ever set. `user-profile`
already requires that a user can "change any single field" (Requirement: Profile inspection,
editing and deletion), but nothing implements it: `/profilo` only displays, and the `modifica`
control addresses diary entries, not the profile. A user who mistyped their birth date during
onboarding, or whose goal weight has since changed, has no way to correct it short of
`/cancellami` — which also destroys every entry they have logged.

Meanwhile the messages people actually write for this ("ora il mio peso obiettivo è 74kg",
"la mia data di nascita è 16/5/72") classify as `other` and reach the advice agent, which is
read-only by design and can only talk about the profile. Worse, the guard that stops a
conversational reply from claiming a write knows the verb family of the diary
(`registrato`/`salvato`/`annotato`) but not that of the profile: `aggiornato`, `impostato` and
`cambiato` pass through it today, so the bot can already claim to have updated a goal it never
touched.

## What Changes

- Add a `profile` intent to classification, making seven. It carries a statement that sets a
  profile field, as distinct from `weight` (which logs a body weight measurement) and from
  `other` (conversation).
- Add a small flat extraction schema that names the field being set and carries the stated
  value verbatim, leaving interpretation to the existing per-field parsing that onboarding
  already uses.
- Confirm before applying. The confirmation states the field, the previous value, the new
  value, and the resulting change to the daily calorie budget, and offers tappable
  confirm/cancel options — the shape the weight intent already uses for a consequential
  scalar.
- Apply the write through the existing `apply_onboarding_field`, so the safety refusals it
  already enforces (a goal weight below BMI 18.5) apply unchanged on this path.
- Extend the false-confirmation guard from entries to profile changes, both in the verb family
  it recognises and in the requirement it enforces.

Not breaking: onboarding, `/profilo`, `/cancellami` and every logging path keep their current
behaviour.

### Non-goals

- **No history for changed profile fields.** A new goal weight overwrites the old one, as the
  other profile columns already do. Whether a changed goal should be dated — the way
  `livello_attivita` already is — is a schema question this change deliberately leaves open.
- **Current weight is not a profile field on this path.** `peso_attuale_kg` writes a
  `WeightEntry`, and the `weight` intent already handles it conversationally. This change adds
  nothing there.
- **The advice agent stays read-only.** Its tools do not gain write access; a profile edit is
  handled by the new intent before the agent is ever reached.

## Capabilities

### New Capabilities

None. Conversational editing belongs to the existing `user-profile` capability, which already
requires it.

### Modified Capabilities

- `user-profile`: the existing "Profile inspection, editing and deletion" requirement gains the
  editing behaviour it names but never specifies — which fields are settable in conversation,
  that a change is confirmed before it is applied, that the confirmation states the budget
  impact, and that the existing goal-weight safety limit refuses an unsafe edit.
- `message-ingestion`: classification enumerates the intents exhaustively and gains `profile`
  as a seventh. "Only the storing path may confirm a record" currently scopes to entries being
  created, amended or deleted; it extends to cover a claim that a profile field was changed.

## Impact

- `src/calobot/ingestion/schemas.py` — `Intent` literal, new extraction schema
- `src/calobot/ingestion/extractors.py` — new extraction prompt
- `src/calobot/ingestion/pipeline.py` — routing for the new intent, confirmation handling
  alongside `_handle_weight_confirmation`
- `src/calobot/persistence/models.py` — a `DraftIntent` value for the pending confirmation
  (Alembic migration, per project convention)
- `src/calobot/profile/service.py` — read-back of a field's current value, and the budget
  before/after the proposed change; the write itself reuses `apply_onboarding_field`
- `src/calobot/safety/claims.py` and `tests/harness/invariants.py` — the profile verb family,
  added to both deliberately independent implementations
- `openspec/specs/user-profile/spec.md`, `openspec/specs/message-ingestion/spec.md`
