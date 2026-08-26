## Why

The current multi-intent classification and extraction logic is overly sensitive. When a user provides a perfectly valid food or activity log but adds conversational fluff (e.g., "li ho registrati nei logs", "ecco i log", or "boh"), the system treats the fluff as an unhandled secondary intent and replies with an intrusive "Ho notato anche: ... non l'ho registrato" warning. Furthermore, vague food entries (e.g., "boh, pasta?") are being misclassified entirely as conversational advice rather than triggering the clarification loop for grams. These issues were discovered via autonomous QA simulations, where UX scored low due to robotic and rigid responses. We need to relax the multi-intent filter to ignore conversational fluff silently, correctly classify vague logs as food intents requiring clarification, and handle contradictions naturally.

## What Changes

- **Relaxed Multi-Intent Warnings:** The system will only warn the user about unrecorded text if that text contains an *actionable* but dropped secondary intent (e.g., another food item, weight log, or activity). Conversational fluff or pleasantries will be ignored silently.
- **Vague Log Classification:** A message stating a single vague food item (e.g., "boh, pasta?") will be classified as a `food` intent missing quantity, not an `other` conversational intent, thereby correctly entering the clarification loop.
- **Contradiction Resolution:** If a user corrects themselves within the same message ("I was going to eat pizza, but I ate a salad"), the extraction layer will resolve the final intent (the salad) instead of treating the discarded item as a secondary unhandled intent or confusing it with an edit of a past entry.

## Capabilities

### New Capabilities

*(None)*

### Modified Capabilities

- `message-ingestion`: Modifying the requirements for "Message mixing two intents" and "Message mixing a loggable intent with conversation" to specify that non-actionable fluff must be ignored silently. Also updating classification rules to ensure vague food inputs trigger clarification rather than conversational advice, and that self-contradictions in a single message are resolved.

## Impact

- **calobot/ingestion/classifier.py**: The LLM prompt or rules for intent classification will need tuning to catch vague logs and ignore fluff.
- **calobot/ingestion/extractor.py**: The prompt that decides what text was "left over" (unhandled) must be updated to only surface actionable intents (e.g., discarded weight or activity logs) rather than literal fluff.
- **tests/harness**: Scenarios testing the multi-intent edge cases will need to be updated to expect silent ignoring of fluff rather than explicit warnings.
