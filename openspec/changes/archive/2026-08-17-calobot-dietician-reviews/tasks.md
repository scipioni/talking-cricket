## 1. Pydantic Schema and Prompt Definitions

- [x] 1.1 Create `src/calobot/reporting/dietician.py` and define the `DieticianReview` Pydantic schema model with required Italian fields
- [x] 1.2 In `src/calobot/reporting/dietician.py`, define the professional clinical Italian nutritionist system prompt (`DIETICIAN_SYSTEM_PROMPT`) targeting calorie density, hour-of-consumption timing, provenance ratios, and logging quality

## 2. Core Dietician Engine

- [x] 2.1 Implement `get_dietician_signals` to extract indirect nutritional signals from a list of `FoodEntry` models (categorizing density, timing hours, and provenance percentages)
- [x] 2.2 Implement `build_dietitian_review` which handles calling `LLMGateway.call_structured` with the compiled signals and prompt, returning a structured review or falling back if logged days < 3
- [x] 2.3 Add unit tests verifying correct computation of calorie density categories, hour extractions, and data provenance ratios on synthetic entries

## 3. Pipeline & UI Integration

- [x] 3.1 Update `_handle_report` in `src/calobot/ingestion/pipeline.py` to check for weekly/monthly periods on food or all reports
- [x] 3.2 Integrate the asynchronous `build_dietitian_review` call into the report generation pipeline, ensuring the Telegram typing indicator stays active during the LLM call
- [x] 3.3 Format the structured JSON schema into a polished Telegram Markdown block in Italian with appropriate bold/bullet styling and emoji highlights

## 4. Testing & Verification

- [x] 4.1 Create `tests/test_dietician_reviews.py` to assert that weekly food reports trigger LLM review requests with the correct JSON context
- [x] 4.2 Add test cases asserting that reporting on periods with under 3 distinct logged days correctly bypasses the LLM and returns the friendly Italian insufficient-data notice
- [x] 4.3 Verify that single-day calorie reports bypass the dietician logic completely and generate immediately as before
