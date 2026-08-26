## Context

See proposal.md. The current implementation in `src/calobot/ingestion/pipeline.py` checks `if not food_report.has_data:` and simply appends `OutgoingMessage(text="Non ci sono dati sul cibo per questo periodo.")`.

We want to replace this with an LLM call so the fallback is conversational and contextual.

## Goals / Non-Goals

**Goals:**
- Replace the hardcoded string with an LLM-generated conversational response.
- Pass the user's daily calorie budget and the requested period into the LLM prompt so it can give helpful context (e.g. "Hai ancora tutte le tue 2000 kcal disponibili per oggi!").

**Non-Goals:**
- We are not changing the core reporting schema or how `food_report.has_data` is calculated.
- We are not creating a new intent; this is purely modifying the response generation of the `report` intent.

## Decisions

### Use the LLMGateway for empty reports
We will inject an LLM call directly into the `report` handling branch in `pipeline.py` when `not food_report.has_data`. We will create a small prompt telling the LLM that the user asked for a report, the diary is empty, and their daily budget is X kcal. We will ask it to respond warmly in Italian.
- *Alternatives considered:* We could route this back through the `advice-agent`, but the advice agent's prompt is heavily skewed toward nutrition Q&A. A dedicated, small zero-shot prompt in `responses.py` (or near the report logic) specifically for "empty diary reports" is cleaner and more deterministic.

## Risks / Trade-offs

- **Latency:** We are replacing a synchronous `if` statement with an asynchronous LLM call. This will add ~1-2 seconds of latency to empty report queries. This is an acceptable trade-off for improved UX, as it matches the latency of all other LLM-backed interactions.
