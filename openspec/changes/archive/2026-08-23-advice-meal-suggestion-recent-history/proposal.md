## Why

When a user asks an ad-hoc question like "cosa mi consigli di mangiare questa
sera?", the advice agent (`src/calobot/advice/agent.py`) already suggests
budget-appropriate recipes via its `RICETTE E SUGGERIMENTI DI PASTI`
instruction block (`specs/advice-agent` - Budget-appropriate meal and recipe
suggestions) - but it only looks at *today's* remaining calories
(`get_profile_and_budget`). It has no instruction to consider what the user
has actually been eating over the last day or two, so it cannot notice "you
haven't had a protein source since yesterday" or "you've eaten mostly
high-density snacks today" the way the weekly dietician review already does
from food descriptions. This under-uses data the bot already has, and misses
exactly the kind of forward-looking, balance-aware advice this project has
just added elsewhere (the day-report's rest-of-day advice, and the tiered
dietician recommendation).

## What Changes

- Add a new read-only advice tool, `get_recent_food_descriptions`, that
  returns food entries (description, kcal, day) for a small number of
  recent days computed server-side relative to today (not absolute dates
  supplied by the model - `list_food_entries` already requires the model to
  produce exact ISO dates, which nothing in the agent's prompt currently
  gives it a reliable way to do, and this proposal does not extend that
  pattern to a new use case).
- Extend `GATHER_SYSTEM_PROMPT` so that, when the question is a meal/recipe
  suggestion, the agent also calls `get_recent_food_descriptions` alongside
  the existing `get_profile_and_budget` call.
- Extend the `RICETTE E SUGGERIMENTI DI PASTI` narration instructions so the
  suggestion also reasons qualitatively about recent variety and apparent
  macronutrient balance (e.g. no protein source lately, everything
  high-density) from those descriptions - the same qualitative,
  description-based reasoning the dietician review and the day-report advice
  already use, under the same existing constraint that Calobot does not
  track macronutrients and must never state a specific gram amount.
- No change to the budget-appropriateness check itself (still driven by
  `remaining_today_kcal`, which already includes the activity credit from
  the `budget-include-activity-kcal` change) - this only adds a second,
  complementary signal.

## Capabilities

### Modified Capabilities

- `advice-agent`: the "Budget-appropriate meal and recipe suggestions"
  requirement is extended so the suggestion also takes recent eating variety
  and apparent macronutrient balance into account, not only today's
  remaining calorie budget.

## Impact

- `src/calobot/advice/tools.py` - new `RecentDaysQuery` args model, new
  `_recent_food_descriptions_handler`, registered as a new tool in
  `build_tool_registry`.
- `src/calobot/advice/agent.py` - `GATHER_SYSTEM_PROMPT` and the `RICETTE E
  SUGGERIMENTI DI PASTI` block in `_narrate_system_prompt` gain instructions
  to use and reason about the new tool's output.
- Tests in `tests/test_advice_tools.py` (new tool's handler) and
  `tests/test_advice_behaviour.py` (agent calls the new tool for a meal
  question and reasons from its output).
