## Why

When a user asks an analytical or theoretical weight-loss question like "Quanti kg avrei dovuto perdere?" (How many kg should I have lost?), the system currently misclassifies the message as a weight `report`. Because the user has no actual weight measurements logged for the queried period, the reporting pipeline responds with "Non ci sono dati sul peso per questo periodo.", completely ignoring the logged food entries and calorie budget. This is highly counter-intuitive because the advice-agent already has the necessary read-only tools to retrieve calorie summaries and calculate theoretical weight loss from the calorie deficit.

## What Changes

- Clarify intent classification rules in `src/calobot/ingestion/classifier.py` so that analytical, theoretical, or advice-seeking queries about weight loss, calorie deficit, or progress (such as *"quanti kg avrei dovuto perdere ?"*, *"perché non dimagrisco ?"*) are classified as `other` (which routes them to the `advice-agent`) rather than `report`.
- Document this routing logic by adding an explicit scenario in the `message-ingestion` specification.
- Add unit tests to ensure these questions are correctly classified as `other` and routed to the advice-agent.

## Capabilities

### New Capabilities

*(None)*

### Modified Capabilities

- `message-ingestion`: Clarify classification rules in the system prompt so that analytical weight-loss or progress questions (like "quanti kg avrei dovuto perdere?") are classified as `other` instead of being misrouted as `report`.

## Impact

- **Affected Code**: `src/calobot/ingestion/classifier.py` (system prompt update).
- **Affected Tests**: `tests/test_advice_behaviour.py` (new test to verify analytical weight advice).
- **Affected Specifications**: `openspec/specs/message-ingestion/spec.md` (new scenario).
