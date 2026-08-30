## Context

The message intent classification is handled via an LLM using a structured prompt defined in `src/calobot/ingestion/classifier.py`.
Standard logs/statistics report commands are handled deterministically in `src/calobot/ingestion/pipeline.py` through `_handle_report`.
Open-ended questions and requests for advice are routed to `src/calobot/advice/agent.py` under the `other` intent, where the advice-agent employs read-only tools like `get_calorie_summary` and `get_profile_and_budget` to retrieve relevant user data and answer.
See `proposal.md - Why` for why the current prompt routing fails on analytical progress questions.

## Goals / Non-Goals

**Goals:**
- Adjust classification system prompt boundaries to ensure analytical progress or weight loss questions are classified as `other` rather than `report`.
- Verify the advice-agent correctly receives, fetches data for, and answers such analytical queries.

**Non-Goals:**
- Creating a new intent type.
- Modifying the deterministic weight or food report logic.
- Adding new tools to the advice-agent.

## Decisions

### Decision 1: Refine boundaries in the Classifier System Prompt
Modify the `SYSTEM_PROMPT` in `src/calobot/ingestion/classifier.py` to explicitly separate standard report commands (`report` intent) from analytical, theoretical, and advice-seeking queries about progress (`other` intent).
We will add specific examples to `other` (such as *"quanti kg avrei dovuto perdere?"*, *"perché non perdo peso?"*) and clarify that `report` is for standard, direct log summaries (such as *"report di oggi"*, *"statistiche peso"*).
*Alternative considered:* Adding a separate `advice` intent. This was rejected because the existing `other` intent already maps cleanly to the advice-agent pipeline, and introducing a new intent would require significant refactoring of the routing pipeline in `pipeline.py`.

### Decision 2: Add behavioral test cases to unit tests
We will add a new test case in `tests/test_advice_behaviour.py` to mock and verify that analytical progress questions are classified as `other`, and that the advice-agent correctly makes tool calls to fetch calorie summaries and profile details to construct its response.

## Risks / Trade-offs

- **[Risk]** Classifier prompt updates could cause regressions in classifying standard report queries.
- **[Mitigation]** Standard report queries (like "report di oggi") have explicit test cases in `test_pipeline_e2e.py` which we will run to ensure no regressions are introduced.
