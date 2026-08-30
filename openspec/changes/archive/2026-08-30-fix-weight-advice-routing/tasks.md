## 1. Classifier Prompt Refinement

- [x] 1.1 Update `SYSTEM_PROMPT` in `src/calobot/ingestion/classifier.py` to explicitly define progress and analytical weight-loss/deficit queries (e.g. "quanti kg avrei dovuto perdere?") under the `other` intent, and keep standard summaries under `report`. Verify the changes are syntactically correct.

## 2. Specification Sync

- [x] 2.1 Add the new scenario `Analytical weight-loss advice question` under `Requirement: Classification of inbound messages` in `openspec/specs/message-ingestion/spec.md` to keep the main specs in sync.

## 3. Testing and Verification

- [x] 3.1 Add a new unit test in `tests/test_advice_behaviour.py` that verifies a query like "quanti kg avrei dovuto perdere?" is classified as `other` and routed to the advice-agent, prompting it to call `get_calorie_summary` and `get_profile_and_budget`. Verify the test passes using `uv run pytest tests/test_advice_behaviour.py`.
- [x] 3.2 Run the full test suite using `task test` to ensure there are no regressions across any existing reporting or advice capabilities.
