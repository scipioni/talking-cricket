## Why

The bot can log food, weight and activity, and it can produce fixed reports with a
dietician review appended. What it cannot do is answer a question it was not built
to anticipate. "Come sono andato rispetto al mese scorso?", "posso permettermi una
pizza stasera?" and "mangio troppo tardi?" each need a different slice of the
user's own data, and that space does not close — every new question shape would
otherwise mean a new hardcoded aggregation.

Today those messages are classified `other` and answered by a single conversational
call that has no access to the diary at all (`safety/conversation.py`). The bot
therefore answers questions about the user's own eating without ever looking at what
they ate, which is the one thing a virtual nutritionist should not do.

## What Changes

- Add a bounded, **read-only** advice agent: an LLM tool-calling loop whose tools
  expose the user's stored data and the existing deterministic aggregators.
- Route the `other` intent to the advice agent instead of directly to the plain
  conversational reply. Greetings and how-do-I questions still get a short answer;
  questions about the user's own data now get one grounded in that data.
- Add native OpenAI tool-calling to `LLMGateway` alongside `call_structured`. No MCP
  server: the database is in-process SQLite, so MCP would add a transport hop to
  reach the bot's own file without exposing anything to an external client.
- Bind the user identity **server-side** for every tool call. `user_id` is never a
  model-supplied parameter, so no prompt can talk the agent into reading another
  user's diary.
- Make tools report absent data explicitly (no macronutrients, no micronutrients,
  too few logged days) so the agent declines instead of estimating.
- Keep both existing deterministic safety guards around the agent: the medical-topic
  refusal before any model call, and the false-confirmation check on the final reply.
- Reuse `build_dietitian_review` as one of the agent's tools rather than writing a
  second nutritionist prompt.

The agent selects *which* numbers to fetch and explains them. It never computes one.
Every figure it reports comes from the same deterministic aggregators that produce
the charts, which is what keeps a report reflecting real changes in eating rather
than the variance of a language model.

**Write and mutation tools are explicitly out of scope for this change.** The
ingestion path stays deterministic: classification, extraction, the clarification
loop and storage are untouched. The tool layer is shaped so write tools can be added
later, but none is added here.

## Capabilities

### New Capabilities

- `advice-agent`: A bounded, read-only tool-calling loop that answers open-ended
  questions about the user's own logged data. Covers the tool contract (read-only,
  server-bound identity, explicit absent-data reporting), the turn and failure
  bounds, refusal behaviour when the data cannot support an answer, and the
  requirement that the model never computes a reported figure.

### Modified Capabilities

- `message-ingestion`: The `other` intent now routes to the advice agent rather than
  straight to a conversational reply, and the language model invocation contract must
  cover an agentic call — bounded tool turns, tool failures, and a final answer that
  is still schema-validated.
- `dietician-reviews`: The review becomes reachable outside the report path, when the
  agent judges it the right answer to a question, still only for periods of a week or
  longer.

## Impact

**Affected code**

- `src/calobot/llm/gateway.py` — new agentic call method; the existing
  `call_structured` is unchanged.
- `src/calobot/ingestion/pipeline.py` — the `other` branch routes to the agent.
- `src/calobot/safety/conversation.py` — becomes the agent's fallback for messages
  that need no data, keeping both guards.
- New: an agent module plus a read-only tool registry wrapping
  `build_calorie_report`, `build_weight_report`, `get_entries_in_range` and
  `build_dietitian_review`.

**Affected tests and tooling**

- `tests/harness/llm.py` — `ScriptedLLM` returns content-only responses and cannot
  express `tool_calls`. It must be extended before any agent test can run. This is a
  prerequisite, not a follow-up.
- Telemetry — `LLMGateway` publishes one `llm_transaction` per call; an agent turn is
  several calls, so the `realtime-monitor` and `activity-export` capabilities need a
  decision on grouping rather than a flood of unrelated-looking events.

**Not affected**

- No schema migration. No change to `Classification`, so no reliance on a
  self-reported confidence field from a model that calibrates them poorly.
- No new runtime dependency: tool-calling is part of the OpenAI-compatible API the
  project already speaks.

**Risk**

The configured model is `qwen3-vl:30b-a3b-instruct` — a mixture-of-experts model with
roughly 3B active parameters, which is markedly less reliable driving a multi-turn
tool loop than doing single-shot constrained JSON, and during tool turns there is no
constrained-decoding guarantee. This is why the loop is bounded, the tool set is
small and whitelisted, the router stays a single flat call, and the agent is confined
to a path where a wrong answer costs one sentence rather than a corrupted diary.
