## 1. New recent-food-descriptions tool

- [x] 1.1 Add a `RecentDaysQuery(BaseModel)` args model (`days: int` bounded 1-5, default 2) in `src/calobot/advice/tools.py`, and verify a unit test rejects an out-of-range value
- [x] 1.2 Add `_recent_food_descriptions_handler(session, user, tz)` computing `[today - days, today + 1)` via `today_in_timezone(tz)` and returning compact `{description, kcal, day}` entries (capped at `MAX_LISTED_ENTRIES`, matching `list_food_entries`'s shape), and verify a unit test covers: entries present, no entries (`no_data: True`)
- [x] 1.3 Register the handler as a new `get_recent_food_descriptions` tool in `build_tool_registry`, with a description distinct from `list_food_entries` ("ultimi N giorni da oggi" vs "intervallo di date preciso"), and verify `test_no_tool_schema_exposes_a_user_identifier` still passes for it (no `user_id`/`telegram` in its schema)

## 2. Wire it into the meal-suggestion path

- [x] 2.1 Add a bullet to `GATHER_SYSTEM_PROMPT` (`src/calobot/advice/agent.py`) instructing the model to also call `get_recent_food_descriptions` when the question is a meal/recipe suggestion
- [x] 2.2 Extend the `RICETTE E SUGGERIMENTI DI PASTI` block in `_narrate_system_prompt` to reason qualitatively from `get_recent_food_descriptions`'s output (apparent lack of a protein source, run of high-density foods) while restating the existing rule to never state a specific macronutrient gram amount
- [x] 2.3 Verify via a behaviour test (`test_advice_behaviour.py`, scripted agentic turn) that a meal-suggestion question triggers a call to `get_recent_food_descriptions` alongside `get_profile_and_budget`, and that the narrated answer reflects a scripted qualitative signal (e.g. no protein source in recent entries) from its output

## 3. Guardrail tests

- [x] 3.1 Add a test asserting no digit-plus-"g" pattern next to a protein/fat/carb word appears in a stubbed narration answer for a meal-suggestion scenario (reuse the regex pattern established in `budget-include-activity-kcal`'s dietician tests, or an equivalent local one)
- [x] 3.2 Verify the existing "Recipe suggestion within budget" and "Recipe suggestion when over budget" behaviour, if covered by existing tests, is unaffected by the new tool call (no regression when `get_recent_food_descriptions` returns no data)

## 4. Final checks

- [x] 4.1 Run `task check` (test, lint, typecheck) and confirm no new failures beyond the pre-existing baseline (documented in `budget-include-activity-kcal`'s tasks.md 6.5): full suite now 447 passed (up from 442) with the same single pre-existing `/data`-permission failure; lint stayed at exactly 8 pre-existing errors in the touched files (0 new); typecheck stayed at the same 5 pre-existing errors (0 new)
