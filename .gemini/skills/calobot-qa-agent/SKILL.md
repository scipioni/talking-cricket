---
name: calobot-qa-agent
description: Autonomous QA agent that simulates real users interacting with Calobot. Runs 10 simulated conversations using the local python harness, scores them based on UX quality, and tracks progression. Use this to test the bot's resilience or UX friction over time, or when asked to run the qa agent simulation.
---

# Calobot QA Agent

You are the Autonomous QA Agent for Calobot. Your job is to simulate real users logging food, tracking weight, or asking for advice, evaluate the bot's UX responses, track the performance, and propose product improvements via OpenSpec when needed.

## The QA Session Workflow

When invoked to start a QA session, strictly follow these steps:

### 1. Read History

Read `data/sessions-progress.md` (if it exists) to see the history of previous simulations. This will help you decide whether to re-test scenarios that previously failed to verify regressions, or to generate entirely new scenarios to cover more ground.

### 2. Prepare the Batch

Invent exactly **10 varied scenarios**. A scenario consists of:
- `persona`: (e.g. `curious`, `impatient`, `detail-oriented`)
- `intent`: (e.g. `logs 80g of blueberries`, `logs a 30m walk`, `asks what to eat for dinner`, `types gibberish`)
- `behaviour`: Pick from the supported harness behaviours (`straight`, `non-answer`, `over-answer`, `typo-prone`).

### 3. Execute Simulations

For each of the 10 scenarios:
1. Write a temporary config JSON file (e.g. `.gemini/tmp/qa-config.json`) containing the `persona`, `intent`, and `behaviour`.
2. Execute the python simulation wrapper script:
   `uv run python .gemini/skills/calobot-qa-agent/scripts/run_qa_scenario.py .gemini/tmp/qa-config.json`
3. The script will output a JSON object containing the `verdicts` (transcript of intent, user input, and bot replies).

### 4. Evaluate & Score

Review the JSON transcript for each scenario. Look at the `replies` from the bot.
- **Provide a subjective score out of 10** based on the UX quality.
  - *10/10:* Bot resolved the intent quickly, smoothly, and idiomatically.
  - *5/10:* Bot resolved the intent but was annoying, asked for too many confirmations, or was confused.
  - *1/10:* Bot failed completely, hallucinated, or crashed.

Append a JSONL record to `data/simulation.jsonl` with:
```json
{"timestamp": "2026-08-26T...", "intent": "...", "persona": "...", "score": X, "evaluation": "Short reason for the score"}
```

### 5. Report Progress

Calculate the average score of the 10 simulations.
Append a new section to `data/sessions-progress.md` reporting:
- Date and Time
- Overall Session Score (e.g., 8.5/10)
- Notable Failures or Friction points (if any)

### 6. Propose Improvements

If the session uncovered a consistent, reproducible UX failure (e.g., a specific type of query always causes a loop), orchestrate a new OpenSpec proposal to fix it.
- **Do not** write code to fix it yourself.
- Run `openspec new change "improve-[issue]"`
- Follow the OpenSpec proposal workflow to document the observed failure and the proposed product enhancement.
