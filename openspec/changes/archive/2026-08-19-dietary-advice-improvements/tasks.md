## 1. Safety Limits & Keyword Guard

- [x] 1.1 Expand the clinical safety keywords list in `src/calobot/safety/medical.py` to include metabolic and cardiovascular conditions (such as `colesterolo`, `pressione`, `ipertensione`, `ipercolesterolemia`).
- [x] 1.2 Add unit tests in `tests/test_safety.py` to verify that these new keywords are correctly flagged by `is_medical_topic()`.

## 2. Advice Agent Prompt Tuning

- [x] 2.1 Update `_narrate_system_prompt` in `src/calobot/advice/agent.py` to include specific instructions for recipe/meal suggestions based on remaining calories (positive balance) and empathetic volume-satiety counseling (negative balance).

## 3. Verification & Integration Tests

- [x] 3.1 Add integration tests in `tests/test_advice_behaviour.py` to verify cardiovascular/metabolic questions are refused immediately on the advice path with standard clinical refusal.
- [x] 3.2 Add integration tests in `tests/test_advice_behaviour.py` to verify recipe suggestions when the user has a positive remaining calorie budget (including remaining calorie value).
- [x] 3.3 Add integration tests in `tests/test_advice_behaviour.py` to verify empathetic suggestions of low-density foods when the user has exceeded their budget (negative balance).
- [x] 3.4 Run the test suite and verify that all workspace and advice agent tests pass cleanly.
