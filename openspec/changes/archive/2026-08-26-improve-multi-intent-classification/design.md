## Context

See proposal.md for motivation. The QA simulations revealed that the intent classification layer is overly sensitive to conversational fluff, treats vague food items as conversation rather than data entry, and mishandles in-message self-contradictions. 

The current intent classifier uses an LLM to populate a `Classification` schema which includes an `ignored_text` field. This field is used to warn the user if a secondary intent was dropped. Currently, the LLM prompt instructs it to put *any* unclassified text into `ignored_text`, causing fluff like "ecco i log" to trigger warnings.

## Goals / Non-Goals

**Goals:**
- Eliminate robotic warnings triggered by non-actionable conversational fluff.
- Route vague food logs into the clarification loop rather than the conversational advice loop.
- Resolve self-contradictions within a single message gracefully.

**Non-Goals:**
- We are not changing the core extraction schemas or the database models.
- We are not building a multi-intent extraction pipeline (the system will still extract only one dominant intent and drop/warn about actionable secondary intents).

## Decisions

### 1. Refine the definition of `ignored_text` in the prompt
We will update the `SYSTEM_PROMPT` in `classifier.py` so that the LLM only populates `ignored_text` if the dropped text contains an *actionable* loggable intent (e.g., another food item, weight, or activity). It will explicitly be instructed to silently ignore conversational fluff, greetings, and pleasantries.
- *Alternatives considered:* We could have added a post-processing step to classify the `ignored_text` again to see if it's fluff. This would add latency and cost. Prompt engineering is more efficient and aligned with our current architecture.

### 2. Explicit rules for vague logs and contradictions
We will add explicit examples to the `SYSTEM_PROMPT` in `classifier.py` to handle edge cases:
- Vague logs ("boh, pasta?") must be classified as `food`.
- Self-contradictions ("volevo registrare X ma ho mangiato Y") must resolve to a single dominant intent (Y), without flagging X as an ignored intent.
- *Alternatives considered:* We could have created a dedicated `contradiction` intent or a separate pre-processing filter. This would overcomplicate the pipeline schema for what is ultimately an NLP comprehension task best handled by the LLM natively.

## Risks / Trade-offs

- **[Risk]** The LLM might silently drop a valid, actionable intent if it mistakes it for conversational fluff. 
  - *Mitigation:* We will provide very clear examples in the prompt distinguishing actionable data ("e ho corso 4km") from fluff ("li ho registrati nei logs").
- **[Risk]** Vague food logs might be missing so much context that the downstream clarification loop struggles to ask the right questions.
  - *Mitigation:* The existing clarification loop is already robust against missing fields. We are simply ensuring the vague log reaches it instead of being hijacked by the advice agent.
