## 1. Implement Conversational Empty Report

- [x] 1.1 In `src/calobot/reporting/responses.py` (or a suitable file), create an async function `generate_empty_report_response(gateway, period, budget, date, tz)` that invokes the LLM to generate a conversational "empty diary" message. Verify the prompt encourages a friendly tone.
- [x] 1.2 In `src/calobot/ingestion/pipeline.py`, update the `report` branch so that when `not food_report.has_data`, it awaits this new function instead of appending the hardcoded string. Verify by running the local bot or running `pytest` to see if it breaks hardcoded string tests.

## 2. Update Tests

- [x] 2.1 Update `tests/test_reporting.py` (and any other test expecting "Non ci sono dati sul cibo per questo periodo.") to expect the new LLM-generated conversational response (or to mock the gateway response if it's a unit test). Verify by running `uv run pytest tests/test_reporting.py`.
- [x] 2.2 Run the `calobot-qa-agent` simulation (or `uv run pytest tests/test_qa_batch2.py -m live -s`) to ensure the "demanding" persona (who asks for a report on an empty diary) now receives a conversational response and scores higher.
