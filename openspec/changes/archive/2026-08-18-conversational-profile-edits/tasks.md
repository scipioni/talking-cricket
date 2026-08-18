## 1. Schema and migration

- [x] 1.1 Add `profile` to `DraftIntent` in `src/calobot/persistence/models.py`
- [x] 1.2 Generate the revision with `task migration -- "add profile draft intent"`, and verify upgrade and downgrade both run against a scratch database

## 2. Classification

- [x] 2.1 Add `profile` to the `Intent` literal in `src/calobot/ingestion/schemas.py`
- [x] 2.2 Extend the classifier prompt to name the new intent, drawing the line against `weight` explicitly: a stated body weight is a measurement, a stated goal weight is a profile field
- [x] 2.3 Probed the real endpoint (qwen3-vl:30b-a3b-instruct) with 10 Italian phrasings: both directions of the weight/profile boundary ("peso 88 kg" → weight, "ora il mio peso obiettivo è 74kg" → profile/peso_obiettivo_kg), each of the 6 settable fields, and non-profile intents for contrast (activity, and "ho perso mezzo chilo" → weight). All 10 classified and extracted as expected; none crossed the boundary either direction.

## 3. Extraction

- [x] 3.1 Add a flat `ProfileEditExtraction` schema: the field name drawn from a fixed set, plus the stated value verbatim — no typed values, per design.md
- [x] 3.2 Add the extraction prompt, listing the settable fields in Italian and instructing that the value be copied verbatim
- [x] 3.3 Add `extract_profile_edit()` in `src/calobot/ingestion/extractors.py`, using the `extract` step

## 4. Proposing the change

- [x] 4.1 Add a read in `src/calobot/profile/service.py` returning a field's current value in displayable form
- [x] 4.2 Add a way to compute the daily budget for a proposed field value without persisting it, so the confirmation can state the before/after delta
- [x] 4.3 Build the confirmation text: field, current value, proposed value, budget change, with confirm/cancel offered as tappable options
- [x] 4.4 Reuse `parse_field_raw` for the stated value; on a parse error, surface its message rather than a generic one

## 5. Applying the change

- [x] 5.1 Route the `profile` intent in `src/calobot/ingestion/pipeline.py` and park a draft awaiting confirmation
- [x] 5.2 Add the confirmation handler alongside `_handle_weight_confirmation`, accepting the same affirmatives and the existing abandon option
- [x] 5.3 Apply through `apply_onboarding_field`, and surface its returned error (the BMI 18.5 refusal) as a refusal that leaves the profile unchanged
- [x] 5.4 Route an unparseable or unusable value back through the clarification loop, respecting `clarification_attempt_limit` rather than looping
- [x] 5.5 Ensure `peso_attuale_kg` is not settable on this path — a current-weight statement stays with the `weight` intent

## 6. False-confirmation guard

- [x] 6.1 Add the profile verb stems (`aggiornat`, `impostat`, `cambiat`) to `src/calobot/safety/claims.py`
- [x] 6.2 Add them independently to `tests/harness/invariants.py` — by hand, without sharing an implementation, per the header on `claims.py`
- [x] 6.3 Confirm the existing negation and question scoping still holds for the new stems on negated and interrogative forms ("non ho aggiornato nulla", "vuoi che aggiorni?"). Note (found during implementation): a plain declarative use like "ti tengo aggiornato" is neither negated nor a question, so it still triggers - this is the false positive design.md's Risks section already names and accepts ("degraded conversation, not wrong data"), not a defect to fix here.

## 7. Tests

- [x] 7.1 Unit: `parse_field_raw` round-trip for each settable field via the new path, including a value that must be refused
- [x] 7.2 Unit: the guard recognises the profile verbs, and does not fire on the negated and interrogative forms from 6.3
- [x] 7.3 End to end: "ora il mio peso obiettivo è 74kg" asks for confirmation stating the old value, the new value and the budget delta, and stores nothing yet
- [x] 7.4 End to end: confirming applies the change and the recomputed budget is reflected in `/profilo`
- [x] 7.5 End to end: declining leaves the profile untouched and says so
- [x] 7.6 End to end: "la mia data di nascita è 16/5/72" resolves to 1972-05-16
- [x] 7.7 End to end: an unsafe goal weight is refused and the stored goal is unchanged
- [x] 7.8 Regression: "peso 88 kg" still logs a weight measurement and does not open a profile draft

## 8. Sync

- [x] 8.1 Ran `task check`: the only failures are the two pre-existing, unrelated issues confirmed present on `main` before this change (a date-dependent test in `test_reporting.py`, and a `mypy` arg-type error in `pipeline.py` unrelated to profile edits) plus pre-existing lint debt in files this change never touches. Nothing this change introduced needed resolving.
- [x] 8.2 Decided yes - discoverability matters and it's a one-line addition. Added a paragraph to `HELP_TEXT` in `src/calobot/telegram/handlers.py`.
- [x] 8.3 Synced the delta specs into `openspec/specs/user-profile/` and `openspec/specs/message-ingestion/`; `openspec validate --specs` passes on all 14 capabilities
