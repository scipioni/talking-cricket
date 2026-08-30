## Why

The advice agent's prescriptive behaviour — meal and recipe suggestions — is encoded
as branching prose inside `_narrate_system_prompt`. Two spec requirements
("Budget-appropriate meal and recipe suggestions", "Empathetic counseling for budget
deficits") are enforced only by that prose, and with the project's stubbed LLM gateway
they cannot be tested: `tests/test_advice_behaviour.py` stubs the model's answer text
and then asserts on its own stub, so the assertions pass regardless of whether the
requirement holds.

The branch the prose agonises over is a pure function of `remaining_today_kcal`, a
figure the code already computes deterministically. Every advice-agent invariant that
is enforced by a code guard (nothing written, no record claimed, medical topics
refused, identity bound outside the conversation) has a test that can fail; every
invariant enforced by prompt prose does not. Further prescriptive depth added the
current way would be depth added with no verification.

## What Changes

- Add a read-only `get_meal_suggestion_context` tool. Its handler deterministically
  derives a **suggestion mode** (`within_budget` / `over_budget` / `no_budget`) and,
  for `over_budget`, a `ceiling_kcal`, from the same budget computation
  `get_profile_and_budget` already uses. The model calling this tool *is* the
  detection that the message is prescriptive — the language judgement stays with the
  model, the branch becomes Python.
- Compose the narration system prompt from a base plus **one mode fragment**, instead
  of one shared prompt containing numbered if/else prose. The union lives in prompt
  selection, not in the response schema.
- Extend `AdviceAnswer` with flat fields (`suggestion_mode`, `suggested_kcal_total`)
  so the branch the model actually took is observable. Schema stays flat — no
  discriminated union — per the gateway constraint in `CLAUDE.md`.
- Add a deterministic guard on the narrated answer, mirroring the existing
  `asserts_a_record` guard: an answer that reports a mode other than the one the tool
  derived, or that declares a suggestion above `ceiling_kcal` in `over_budget` mode,
  is suppressed and replaced with a safe deterministic reply.
- Remove the "usa SEMPRE sia `get_profile_and_budget` sia
  `get_recent_food_descriptions`" instruction from `GATHER_SYSTEM_PROMPT` and the
  `RICETTE E SUGGERIMENTI DI PASTI` block from `_narrate_system_prompt`; both are
  replaced by the mechanisms above.
- Resolve a live contradiction between two current advice-agent requirements:
  "Reported figures come from deterministic computation" forbids the model from
  computing any figure it presents, while "Budget-appropriate meal and recipe
  suggestions" asks it to propose dishes "whose estimated calories do not exceed the
  remaining balance". The determinism requirement is scoped to figures about the
  user's *logged* data; calories of a not-yet-eaten suggested dish are an estimate,
  which must be framed as approximate, is never stored, and is never mixed into a
  logged total.
- Replace the tautological recipe tests with tests that assert the derived mode and
  the selected prompt fragment — assertions that depend on code, not on a stub.

Not breaking: the user-visible shape of a suggestion answer is unchanged when the
model behaves as it does today. `no_budget` mode reproduces current behaviour for an
incomplete profile.

## Capabilities

### New Capabilities

None. This adds no user-visible capability; it moves existing prescriptive behaviour
from prose to code and makes it verifiable.

### Modified Capabilities

- `advice-agent`: the two prescriptive requirements are restated in terms of a
  deterministically derived suggestion mode and an enforced ceiling rather than model
  compliance with instructions; the determinism requirement is scoped to figures about
  logged data, with an explicit carve-out for suggested-dish estimates.

## Impact

- `src/calobot/advice/tools.py` — new `get_meal_suggestion_context` tool and its
  args/result models; `get_profile_and_budget` retained unchanged for non-prescriptive
  budget questions.
- `src/calobot/advice/agent.py` — `GATHER_SYSTEM_PROMPT` and `_narrate_system_prompt`
  restructured; `AdviceAnswer` extended; new guard alongside `asserts_a_record`.
- `tests/test_advice_behaviour.py`, `tests/test_advice_tools.py` — recipe tests
  rewritten against the derived mode; new tests for the ceiling guard.
- No database schema change, no migration, no new dependency.
- No change to the classifier or `message-ingestion`: the intent remains `other`.
