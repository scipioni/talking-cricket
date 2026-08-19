## Why

Enhance the advice agent's conversational capabilities to safely suggest healthy, budget-appropriate recipes and nutritional advice (such as increasing vegetable intake for satiety) while strengthening the automated medical guardrails to refuse requests about metabolic and cardiovascular clinical conditions.

## What Changes

- **Recipe & Meal Suggestions**: Support requests like "cosa posso mangiare stasera?" by enabling the agent to combine user-specific context (remaining daily calorie budget) with general nutritional best practices to suggest realistic, healthy, Italian-style recipe ideas.
- **Empathetic Over-Budget Behavior**: Instruct the agent to handle budget deficits gracefully—instead of encouraging meal-skipping, it will suggest very low-density, high-volume foods (e.g., raw vegetables or clear broths) to provide comfort and volume satiety safely.
- **Expanded Medical/Clinical Guardrails**: Expand the deterministic keyword guard to automatically block questions relating to metabolic and cardiovascular health (e.g., cholesterol, hypertension, blood pressure) which require therapeutic, clinician-prescribed diets.

## Capabilities

### New Capabilities
<!-- Capabilities being introduced. Use kebab-case for path segments you introduce
     (e.g., user-auth or identity/user-auth) that follow the project's existing
     spec organization. Each creates specs/<capability-path>/spec.md. -->

### Modified Capabilities
<!-- Existing capabilities whose REQUIREMENTS are changing (not just implementation).
     Only list here if spec-level behavior changes. Each needs a delta spec file.
     Use the exact existing path under openspec/specs/. Leave empty if no requirement
     changes. A change with no capabilities at all (pure refactor, tooling, docs)
     must set `skip_specs: true` in its .openspec.yaml - openspec validate rejects
     a zero-delta change without that marker. Do not invent a requirement just to
     satisfy validation. -->
- `advice-agent`: Update existing safety limits to block metabolic/cardiovascular terms, and specify the behavior for recipe suggestions and over-budget counseling.

## Impact

- **`src/calobot/safety/medical.py`**: Adding keywords like `colesterolo`, `pressione`, `ipertensione`, `ipercolesterolemia` to `MEDICAL_KEYWORDS`.
- **`src/calobot/advice/agent.py`**: Tuning `_narrate_system_prompt` to provide guidelines on recipe suggestions fitting the user's remaining calories, and empathetic coaching for calorie budget deficits.
- **Unit and behavioral tests**: Add test cases to `tests/test_safety.py` and `tests/test_advice_behaviour.py` to verify refusal of cholesterol/blood pressure questions, and recipe suggestion logic.
