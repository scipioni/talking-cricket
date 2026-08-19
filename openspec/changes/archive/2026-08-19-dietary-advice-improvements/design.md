## Context

See `proposal.md` for motivation. Under the current codebase, the advice agent handles all open-ended questions using a two-phase loop:
1. **Gather Phase**: Selectively calls read-only tools to query the database.
2. **Narration Phase**: Translates results into a natural, empathetic response.

We need to safely extend this model to handle meal suggestions within the calorie budget, address over-budget scenarios empathetically, and deterministically prevent metabolic/cardiovascular counseling.

## Goals / Non-Goals

**Goals:**
- Deterministically block therapeutic metabolic/cardiovascular counseling (e.g., cholesterol, blood pressure) at the keyword-filtering layer.
- Guide the advice agent to safely recommend budget-appropriate meal suggestions.
- Ensure the agent handles negative calorie balances empathetically without encouraging fasting or disordered eating.

**Non-Goals:**
- We are not integrating any external recipe API; the model will use its general knowledge combined with the user's specific remaining calorie budget.
- We are not expanding database models or schemas; all calculations will leverage the existing profile, food, and weight aggregations.

## Decisions

### Decision 1: Determinstic Filtering of Metabolic/Cardiovascular Topics
- **Approach**: Add key terms like `colesterolo`, `pressione`, `ipertensione`, `ipercolesterolemia` directly to `MEDICAL_KEYWORDS` in `src/calobot/safety/medical.py`.
- **Rationale**: Relying on the LLM to identify and refuse cardiovascular or metabolic questions is risky and susceptible to jailbreaks or alignment drifts. A hard deterministic check ensures complete safety before any LLM execution occurs.
- **Alternatives Considered**: Directing the LLM through system prompts to self-refuse. Rejected for lack of deterministic safety.

### Decision 2: Contextual Prompt Engineering for Budget-Appropriate Recipes
- **Approach**: Update the Narration System Prompt (`_narrate_system_prompt` in `src/calobot/advice/agent.py`) with explicit rules on recipe suggestions. If the user asks for meal suggestions, the model must read the `remaining_today_kcal` from the tool output and provide healthy, realistic options that fit within that figure.
- **Rationale**: This leverages the existing `get_profile_and_budget` tool and combines personal data constraints with the LLM's vast general knowledge of cooking.
- **Alternatives Considered**: Building a dedicated SQL-backed database of recipes. Rejected as it adds massive development overhead for a feature that the LLM is already highly capable of handling dynamically.

### Decision 3: Empathetic Counseling for Calorie Deficits
- **Approach**: Instruct the Narration LLM to detect if remaining calories are zero or negative. If so, it must provide supportive, non-judgmental guidance and suggest highly volumetrically satisfying, low-density foods (under 100 kcal/100g, such as broths or crisp vegetables) instead of endorsing skipping meals.
- **Rationale**: Prioritizes psychological safety and promotes healthy habits, completely mitigating the risk of promoting eating-disorder-like behaviors (fasting/starving to offset over-eating).
- **Alternatives Considered**: Refusing to answer when over budget. Rejected as it provides a poor, unhelpful user experience.

## Risks / Trade-offs

- **[Risk]** Deterministic keywords like `pressione` might block benign questions (e.g., "come influisce la pressione atmosferica sul peso?").
  - *Mitigation*: The likelihood of such questions is extremely low in a food-diary context, and maintaining high clinical safety outweighs this rare edge case.
- **[Risk]** The model might hallucinate the calorie counts of suggested recipes.
  - *Mitigation*: Prompt instructions will direct the model to suggest simple, clear-cut recipes and state approximate, realistic calories.
