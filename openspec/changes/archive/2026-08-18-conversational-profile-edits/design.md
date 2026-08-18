# Design: conversational profile edits

## Context

See proposal.md - Why. The relevant constraint is that the machinery this change needs
mostly exists already and is reachable without modification:

- `profile/onboarding.py` holds `parse_field_raw(field, text) -> (value, error)`, a
  deterministic per-field parser (`parse_data_nascita`, `parse_weight_kg`, `parse_ritmo`, …)
  that turns raw Italian text into a typed, range-checked value.
- `profile/service.py` holds `apply_onboarding_field(session, user, field, value)`, the single
  validated write path for all seven fields, including the goal-weight refusal.
- `profile/service.py` holds `current_budget(session, user)`, which recomputes the daily target
  from the profile as it currently stands.
- The pipeline already runs a confirm-then-apply loop for a consequential scalar: the weight
  intent parks a draft and resolves it in `_handle_weight_confirmation`.

What does not exist is a way for a non-onboarding message to reach any of it.

Two constraints from the project's conventions bear directly on this change. Schema changes go
through Alembic, never `create_all` - and `Draft.intent` is a SQLAlchemy `Enum(DraftIntent)`
column, so a new member is a schema change. And `safety/claims.py` carries a header forbidding
its merge with `tests/harness/invariants.py`: the guard and the check that verifies the guard
are deliberately independent implementations, so a change to the recognised verb family has to
be made twice, on purpose.

## Goals / Non-Goals

**Goals:**

- Keep every interpretation of a stated *value* deterministic. The language model names the
  field; it does not parse dates or weights.
- Reuse the existing write and validation path rather than adding a second one, so a safety
  limit cannot hold on one path and not the other.
- Make the consequence of the edit visible before it is applied, since every profile field
  feeds the daily budget.

**Non-Goals:**

- No new capability boundary. This is the `user-profile` capability finally doing what its spec
  already requires.
- No write access for the advice agent, and no change to its tools.
- No general "edit anything" surface. The settable fields are exactly the seven onboarding
  fields, minus the special case noted in Decisions.

## Decisions

### A new intent, not write tools on the advice agent

The literal reading of "edit via the agent" would be to give `advice/tools.py` a mutating tool.
Rejected. `advice-agent/spec.md` requires the agent's data access to be read-only, and that
requirement is load-bearing rather than incidental: the agent has an unbounded natural-language
surface, user-controlled text (food descriptions) flows into its context, and `safety/claims.py`
exists precisely because the agent cannot be trusted to describe its own actions. Today the
worst outcome of a bad agent turn is a wrong answer; with a write tool it becomes a wrong
mutation, and the guard's job would invert from "suppress claims of writing" to the much harder
"verify the claim matches what was written".

A seventh intent instead keeps the mutation on the deterministic path, where the draft
lifecycle, the confirmation loop and the abandon/give-up handling already live.

**Alternative considered:** extending the `correction` capability. Rejected because its service
is entry-shaped (`find_entry_by_confirmation_message`, `amend_food_quantity`, `undo_last`) and
because "la mia data di nascita è 16/5/72" does not correct a previous message - it states a
fact.

### Extraction names the field and quotes the value; parsing stays deterministic

The extraction schema stays flat and small, per the project's rule that this model degrades on
clever schemas: one field name drawn from a fixed set, plus the value verbatim as the user wrote
it. `parse_field_raw` then does the interpretation, and returns an error the loop can re-ask
with.

This keeps the failure modes separate and legible. A model that names the wrong field produces
a confirmation the user can decline; a model that mangles a date cannot, because it never
touches the date. It also means "16/5/72" is handled by the same code that already handles it
during onboarding, rather than by a second interpretation that could drift from the first.

**Alternative considered:** having extraction return typed values directly. Rejected - it would
duplicate `parsing.py` inside a prompt and put date interpretation in the least reliable
component.

### Confirm before applying, and state the budget delta

The weight intent's confirm-then-apply shape is the precedent, and it fits for the same reason:
the value is a consequential scalar that is tedious to undo. Food entries store immediately and
attach a `🗑 elimina` control, but an entry is one row among many, whereas a profile field is
the thing every future budget is computed from.

The confirmation states the field, the current value, the proposed value and the resulting
budget change, because the budget delta is the part the user actually experiences. This is
computable before the write by evaluating `current_budget` against the proposed value.

**Alternative considered:** apply immediately with an undo button, matching the food path.
Rejected on the grounds above, and because an undo control on a profile field would need its own
storage of the previous value.

### Current weight is not settable on this path

Of the seven onboarding fields, `peso_attuale_kg` does not write a profile column at all - it
writes a `WeightEntry`, one per day. The `weight` intent already handles that conversationally.
So a statement of current weight must continue to classify as `weight`, and the classifier
prompt has to draw that line explicitly, because "peso 74" and "peso obiettivo 74" differ by one
word and land in different capabilities. A spec scenario pins the boundary in both directions.

### A changed goal weight overwrites, with no history

`peso_obiettivo_kg` is a column on `User` and stays one. This is a deliberate asymmetry with
`livello_attivita`, which is append-only with `effective_from` because its history is needed to
compute past budgets correctly.

The trade-off is real and is recorded here rather than hidden: reporting projects toward the
goal, so a goal changed mid-period makes a report spanning that period ambiguous. Accepted for
now because dating the goal is a schema change that can be made later without invalidating
anything this change establishes, and because the alternative front-loads a migration and a
"which goal applied when" question into a change whose point is to let a user fix a typo.

### The claim guard grows a second verb family, in both implementations

`asserts_a_record` recognises the diary's verbs (`registrat`, `salvat`, `annotat`, `modificat`,
…). A profile edit uses a different family - `aggiornat`, `impostat`, `cambiat` - and today
those pass through, which means the bot can already claim to have updated a goal it never
touched. This is a live gap independent of the rest of the change.

The stems go into `safety/claims.py` **and** into `tests/harness/invariants.py`, separately and
by hand. The header on the former forbids sharing the implementation, because a shared defect
would make the guard fail to fire and the invariant fail to notice it at the same moment.

## Risks / Trade-offs

- **The classifier confuses `weight` and `profile`.** "peso 74" logs a measurement, "peso
  obiettivo 74" sets a goal, and a misclassification writes the wrong thing → The two scenarios
  in the message-ingestion delta pin both directions. Note that the suite stubs the model, so
  they verify routing given a classification, not the classification itself; a probe against the
  real endpoint during implementation is the only thing that checks the boundary holds.

- **A model-named field the user did not mean.** The confirmation is the mitigation: nothing is
  written until the user agrees, and the confirmation names the field explicitly rather than
  saying "fatto".

- **The guard's new stems produce false positives.** `aggiornato` is a common word ("ti tengo
  aggiornato"), and over-triggering replaces a good conversational reply with a canned one →
  The existing implementation already scopes negation by clause and exempts questions; the new
  stems inherit that. The failure is degraded conversation, not wrong data, which is the right
  direction for this guard to fail in.

- **A seventh intent enlarges the classification surface for every message**, including a
  latency cost on messages that are none of the seven → Accepted; classification is already a
  single call and gains one enum member, not a second call.

## Migration Plan

One Alembic revision adding `profile` to the `DraftIntent` enum used by `Draft.intent`
(`task migration -- "add profile draft intent"`). No data migration: existing drafts keep their
current intents, and a draft is short-lived by design (`draft_expiry_minutes`). Rollback is the
reverse revision; a pending profile draft at rollback time would fail to load, which the expiry
window bounds.

## Open Questions

- Should `/profilo` advertise that fields can be changed by stating them, or is discovery
  through natural use enough? Affects one help string, not the specs or the approach.
