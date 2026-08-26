## Why

When a user asks for a daily calorie report (e.g. "Quante calorie mi rimangono?") and they haven't logged any food yet, the bot returns a hardcoded, robotic string: "Non ci sono dati sul cibo per questo periodo." This creates a jarring UX break in an otherwise highly conversational application. We need to replace this static fallback with a dynamic, LLM-generated conversational response that correctly answers the user's intent (e.g. "You haven't logged anything yet today, so you have your full 2300 kcal budget remaining!").

## What Changes

- **Conversational Fallback for Empty Reports:** When a food report determines there is no data for the requested period (e.g., `not food_report.has_data`), instead of yielding a hardcoded string, the ingestion pipeline will request a conversational response from the LLM (likely via the existing advice agent or a similar prompt).
- The prompt for this fallback will inform the LLM of the user's daily budget, the current date/time, and the fact that the diary is empty for the requested period, instructing it to answer the user's report query conversationally.

## Capabilities

### New Capabilities

*(None)*

### Modified Capabilities

- `reporting`: Modifying the "Period with no data at all" requirement under "Calorie report contents". Instead of saying there is no data in a generic/dry way, the system SHALL respond conversationally, addressing the user's query while stating that the diary is empty and acknowledging their full remaining budget if applicable.

## Impact

- **calobot/ingestion/pipeline.py**: The execution block handling `not food_report.has_data` will need to invoke the LLM gateway instead of appending the hardcoded `OutgoingMessage`.
- **tests/harness/scenario.py**: Any test expecting the exact string `"Non ci sono dati sul cibo per questo periodo."` will need to be updated.
