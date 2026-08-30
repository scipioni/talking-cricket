## 1. Deterministic suggestion context

- [x] 1.1 Add an `OVER_BUDGET_CEILING` constant (100) and a `SuggestionMode` literal
  (`within_budget` / `over_budget` / `no_budget`) to `src/calobot/advice/tools.py`, and
  verify `task typecheck` passes with the literal referenced from a type annotation
- [x] 1.2 Add a `_meal_suggestion_context_handler` that reuses the same
  `current_budget` + `build_activity_report` + `build_food_report` path as
  `_profile_and_budget_handler` to compute `remaining_today_kcal`, then derives
  `mode` and `ceiling_kcal` per design.md Decision 1 (`budget is None` → `no_budget`;
  `remaining > 0` → `within_budget`, ceiling = remaining; `remaining <= 0` →
  `over_budget`, ceiling = `OVER_BUDGET_CEILING`) — verify with unit tests in
  `tests/test_advice_tools.py` covering positive, exactly-zero, negative and
  no-profile cases
- [x] 1.3 Have the same handler return the recent food descriptions (reusing the
  `_recent_food_descriptions_handler` logic, capped by `MAX_LISTED_ENTRIES`) so one
  call supplies both the balance and the variety signal — verify a tool test asserts
  both keys are present in a single result, and that `no_data` is reported rather
  than omitted when no recent entries exist
- [x] 1.4 Register the handler as a `get_meal_suggestion_context` tool (`NoArgs`
  schema) in `build_tool_registry`, with a description scoped to "cosa posso mangiare"
  and distinct from `get_profile_and_budget`'s "quante calorie restano" — verify a
  test asserts both tools are offered and that neither args schema exposes a user
  identifier

## 2. Mode-composed narration prompt

- [x] 2.1 Extract the current `_narrate_system_prompt` body minus its `RICETTE E
  SUGGERIMENTI DI PASTI` block into a base prompt — verify existing non-prescriptive
  tests in `tests/test_advice_agent.py` and `tests/test_advice_behaviour.py` still
  pass unchanged
- [x] 2.2 Add one prompt fragment per mode (`within_budget`, `over_budget`,
  `no_budget`) carrying only that situation's guidance, with the over-budget fragment
  stating the ceiling and the no-fasting rule, and the `no_budget` fragment not
  stating or implying a remaining balance — verify each fragment is a separate module
  constant asserted by name in a test
- [x] 2.3 Change `_narrate_system_prompt(bot_label)` to
  `_narrate_system_prompt(bot_label, mode)` returning base plus exactly one fragment,
  with `mode = none` appending nothing — verify a unit test asserts the composed
  prompt contains the expected fragment and none of the others
- [x] 2.4 In `answer()`, read the derived mode and ceiling out of the gather phase's
  tool results and pass the mode to `_narrate_system_prompt` — verify a behaviour test
  seeds a user 150 kcal over budget, runs the turn, and asserts the over-budget
  fragment is present in the system prompt the stubbed gateway received

## 3. Schema and guard

- [x] 3.1 Extend `AdviceAnswer` with `suggestion_mode` (flat `Literal`, default
  `"none"`) and `suggested_kcal_total` (`int | None`, default `None`) per design.md
  Decision 3 — verify `task typecheck` passes and an existing non-prescriptive test
  still succeeds with both fields defaulted
- [x] 3.2 Add deterministic per-mode fallback texts for a suppressed suggestion
  answer, distinct from `UNFOUNDED_CLAIM_REPLACEMENT` and reading as a plain answer
  rather than a diagnostic — verify a test asserts each text contains no error
  wording and no blame directed at the user
- [x] 3.3 Add a guard alongside `asserts_a_record` in `answer()` that suppresses the
  reply when `result.suggestion_mode` differs from the derived mode, or when the mode
  is `over_budget` and `suggested_kcal_total` exceeds `ceiling_kcal`, logging at
  warning level — verify tests cover a mode mismatch and an over-ceiling declaration,
  each asserting the fallback text is delivered instead
- [x] 3.4 Confirm the guard leaves non-prescriptive answers untouched (mode `none`,
  `suggested_kcal_total` `None`) — verify the greeting and own-eating tests in
  `tests/test_advice_agent.py` pass without modification

## 4. Remove the superseded prose

- [x] 4.1 Delete the "usa SEMPRE sia `get_profile_and_budget` sia
  `get_recent_food_descriptions`" instruction from `GATHER_SYSTEM_PROMPT`, replacing
  it with a single line pointing at `get_meal_suggestion_context` — verify no test
  asserts on the removed wording and `task test` passes
- [x] 4.2 Delete the `RICETTE E SUGGERIMENTI DI PASTI` block from the narration
  prompt now that the fragments carry it — verify the base prompt contains no
  numbered branch logic and no `remaining_today_kcal` reference
- [x] 4.3 Confirm `get_profile_and_budget` and `get_recent_food_descriptions` remain
  registered and unchanged for non-prescriptive questions — verify a test asks
  "quante calorie mi restano oggi?" and asserts no mode fragment was appended

## 5. Replace the tautological tests

- [x] 5.1 Rewrite `test_recipe_suggestion_within_budget` and
  `test_recipe_suggestion_when_over_budget_provides_empathetic_counseling` in
  `tests/test_advice_behaviour.py` to seed real entries and assert on the derived mode
  and the selected prompt fragment rather than on strings hardcoded in their own stubs
  — verify each test fails when the derivation threshold is deliberately inverted
- [x] 5.2 Rewrite `test_recipe_suggestion_considers_recent_food_variety` and
  `test_recipe_suggestion_narration_has_no_macro_gram_claim` against the single
  `get_meal_suggestion_context` call — verify both assert on the tool result contents
  and the fragment, not on stubbed answer text
- [x] 5.3 Note in the over-budget test that its prompt wording ("sono fuori budget")
  no longer selects the branch — add a test where the user's stated situation
  contradicts the computed balance and assert the computed balance governs, covering
  the spec scenario "User misstates their own situation"

## 6. Spec coverage and final check

- [x] 6.1 Add tests for the remaining new spec scenarios not yet covered: "Remaining
  balance is exactly zero", "Profile incomplete so no budget exists", and "Suggestion
  is not treated as a log entry" (asserting `run.assert_clean()` and unchanged
  totals) — verify each maps to a named scenario in the delta spec
- [x] 6.2 Run `openspec validate advice-suggestion-modes --strict` and confirm every
  scenario in the delta spec has a corresponding test
- [x] 6.3 Run `task check` (test, lint, typecheck) and verify all three pass with no
  new `mypy` suppressions added to `pyproject.toml`
