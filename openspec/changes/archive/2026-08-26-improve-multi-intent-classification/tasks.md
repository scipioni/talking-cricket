## 1. Intent Classification Adjustments

- [x] 1.1 Update the `SYSTEM_PROMPT` in `src/calobot/ingestion/classifier.py` to instruct the LLM to only populate `ignored_text` with actionable secondary intents, and ignore conversational fluff silently. Verify by running the QA suite.
- [x] 1.2 Add explicit examples to the `SYSTEM_PROMPT` in `src/calobot/ingestion/classifier.py` demonstrating that vague foods (e.g. "boh, pasta?") belong to the `food` intent and self-contradictions resolve to the final intent. Verify by reviewing the prompt formatting.

## 2. Test Verification

- [x] 2.1 Run the `calobot-qa-agent` simulation (or `uv run pytest tests/test_qa_batch.py -m live -s`) to ensure the previously failing UX interactions (chatty, indecisive, vague, tired, hurried personas) now behave properly without aggressive warnings or misclassification.
