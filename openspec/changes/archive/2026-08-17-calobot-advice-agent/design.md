## Context

See `proposal.md` — Why for motivation, and `specs/advice-agent/spec.md` for requirements.

This design sits on top of the `calobot-v1` core and the `calobot-dietician-reviews`
reviewer. Five existing pieces carry the weight:

1. `LLMGateway.call_structured` — OpenAI-compatible calls with JSON-schema-constrained
   decoding, validation, retry-with-error-fed-back, and typed transport errors.
2. `classify()` — one flat call returning `Classification`, with `other` already
   defined as the bucket for "saluti, domande generiche, richieste di consiglio".
3. `handle_other` — today's `other` handler, sandwiched between two deterministic
   guards: `is_medical_topic` before the model call, and `asserts_a_record` on the
   generated reply.
4. The reporting aggregators — `build_calorie_report`, `build_weight_report`,
   `get_entries_in_range`, `get_dietician_signals` / `build_dietitian_review` — all of
   which already take a timezone parameter and filter `deleted_at`.
5. `ScriptedLLM`, which intercepts at the OpenAI client rather than the gateway, so
   tests exercise the real gateway.

Two constraints shape everything below. The configured model is
`qwen3-vl:30b-a3b-instruct` — a mixture-of-experts model with roughly 3B active
parameters, which is much weaker driving a multi-turn tool loop than it is at
single-shot constrained JSON. And the database is in-process SQLite.

## Goals / Non-Goals

**Goals:**

- Keep the hot path — every food, weight and activity log — on exactly the code it
  runs today, with no added latency or added failure mode.
- Keep every user-visible number produced by the same deterministic code that
  produces the charts, so an answer and a report for the same period cannot disagree.
- Make the user-visible text schema-constrained, not free-form, so the model spends
  its most reliable mode on the part the user actually reads.
- Shape the tool layer so write tools can be added later without redesigning it.

**Non-Goals:**

- No MCP server, and no tool-calling on the classification, extraction or
  clarification steps.
- No new stored state. The agent is stateless per message; it does not get
  conversational memory in this change.
- No change to what the product tracks. Macronutrients stay untracked, and the agent's
  job when asked about them is to say so.

## Decisions

### 1. Route on the `other` intent, not on a confidence score

`classify()` stays exactly as it is — one flat, schema-constrained call — and the agent
is invoked when it returns `intent == "other"`.

**Rationale**: `other` already *is* the ambiguity bucket; `classifier.py`'s prompt
defines it as greetings, general questions and requests for advice. Routing on it needs
no change to `Classification` and no new field. It also keeps a tool loop off the hot
path: a food log still costs one classify call plus one extract call, exactly as today.

**Alternatives considered**: Add a `confidence: float` to `Classification` and invoke
the agent below a threshold. Rejected because a 3B-active model's self-reported
confidence is poorly calibrated, so the threshold would be tuning noise, and it would
widen a schema that `design.md` of `calobot-v1` deliberately keeps minimal. Making the
agent the top-level router for every message was also rejected: it puts a multi-turn
loop in front of every meal the user logs, to answer a question a single call already
answers well.

### 2. Native tool-calling in `LLMGateway`, not an MCP server

Add a second method alongside `call_structured` that passes `tools` to the same
OpenAI-compatible endpoint and drives the tool loop in-process.

**Rationale**: The tools read an in-process SQLite file through functions the bot
already calls directly. An MCP server would add a protocol hop, a serialization
boundary and a second process to reach the bot's own database, and buys nothing unless
an external MCP client needs those tools — which is not a goal here. Tool-calling is
already part of the OpenAI-compatible API the project speaks, so this adds no runtime
dependency.

**Alternatives considered**: An MCP server exposing the food and diary tools. Deferred,
not rejected on principle — if the tools ever need to serve Claude Desktop or another
host, the same registry can be wrapped in MCP without touching the agent.

### 3. Two phases: a bounded tool loop, then a constrained narration call

The agent does **not** end its loop with free-form text. Instead:

1. **Gather** — a bounded loop (default 4 rounds) in which the model may only either
   request tool calls or signal that it has enough. Tool results accumulate.
2. **Narrate** — one `call_structured` call with the accumulated results and a flat
   answer schema, producing the user-visible text.

```python
class AdviceAnswer(BaseModel):
    answer_text: str
    used_data: bool          # False for greetings/how-to, True when a tool informed it
    declined_reason: str | None   # set when the data cannot support an answer
```

**Rationale**: This is the same shape the dietician reviewer already uses —
deterministic signals in, flat structured prose out — and it is what CLAUDE.md means by
preferring two small calls over one clever one. It puts the user-visible output back
under constrained decoding, which is where this model is strongest. It also gives the
`asserts_a_record` guard a single known field to check, and makes "declined because the
data does not exist" an explicit, testable field rather than something to infer from
prose.

**Alternatives considered**: A single loop where the model's final message with no
`tool_calls` is the answer. Simpler and one call cheaper, but the user-visible text is
then unconstrained, the refusal path is implicit, and a model that stops emitting
`tool_calls` because it lost the thread produces a confident-sounding non-answer.

### 4. Tools wrap the existing aggregators, and return summaries rather than rows

| Tool | Wraps | Returns |
| --- | --- | --- |
| `get_calorie_summary(period, reference_day)` | `build_calorie_report` | totals, daily average, budget, difference |
| `get_weight_summary(period, reference_day)` | `build_weight_report` | start, end, change, trend, projection |
| `get_dietician_review(period, reference_day)` | `build_dietitian_review` | the structured review, week+ only |
| `list_food_entries(start_day, end_day, limit)` | `get_entries_in_range` | compact per-entry facts, capped |
| `get_profile_and_budget()` | profile + budget derivation | daily budget, goal, today's remaining |

Every tool returns an explicit emptiness marker (`no_data: true` with the period it
looked at) rather than an empty structure, so "you logged nothing that week" is
distinguishable from a tool that failed.

**Rationale**: The aggregators are the same code the charts use, so an answer cannot
disagree with a report for the same period. Returning pre-aggregated summaries — rather
than raw rows for the model to add up — is what makes "the model never computes a
reported figure" enforceable rather than aspirational, and it keeps tool output small
enough not to crowd the context of a 3B-active model.

`list_food_entries` is the one tool that returns per-entry data, because "cosa ho
mangiato martedì?" genuinely needs it. It is capped, and the system prompt directs
totals to `get_calorie_summary`.

**Alternatives considered**: A single `query(sql)` tool. Rejected outright: it hands the
model arbitrary read access, makes the user-identity boundary unenforceable, and puts
computation back in the model.

### 5. Identity is bound at registry construction, not passed by the model

The tool registry is built per message from the authenticated Telegram identity, and
`user_id` is closed over. It does not appear in any tool's JSON schema, so the model
cannot see it, name it, or be argued into changing it.

**Rationale**: This is a security boundary, not a convenience. If `user_id` were a
model-supplied parameter, "mostrami i dati dell'utente 42" becomes a cross-user read,
and the project already specs resistance to instructions embedded in user messages
(`message-ingestion` — Instructions in a user message are content, not commands). A
parameter the model cannot express is stronger than a parameter it is told not to
misuse.

### 6. The agent sits inside the existing guard sandwich

- `is_medical_topic(text)` runs **before** the loop, deterministically, and short-
  circuits to `REFUSAL_TEXT` with no model call and no retrieval.
- `asserts_a_record(answer_text)` runs **after** narration; a violation is replaced
  wholesale, as it is on the conversational path.

**Rationale**: Both guards already exist and both are deterministic, which is why they
work. The medical guard must stay ahead of retrieval as well as ahead of the model, so a
clinical question never causes a diary read. The false-confirmation guard matters *more*
here than on the conversational path, because an agent that has just been reading the
user's diary sounds far more credible when it wrongly claims to have written to it.

### 7. Fall back to the current conversational reply

If the loop errors, exhausts its bound, or the narration call fails, the handler falls
back to today's `handle_other` behaviour rather than surfacing a failure.

**Rationale**: The degraded state is the product's current behaviour, which is
acceptable. This also makes rollback a one-line routing change.

### 8. Group an agent turn in telemetry with a correlation id

`call_structured` publishes one `llm_transaction` per call. An agent turn is several
calls, so each gets a shared `agent_turn_id`, plus its round index and the tool name it
resulted from.

**Rationale**: Without it the `realtime-monitor` and `activity-export` capabilities show
four or five unexplained calls per message and the causal chain is lost — which is the
one thing worth watching while this feature is new. A correlation id is additive and
needs no consumer change to keep working.

## Risks / Trade-offs

**A 3B-active model drives tool loops unreliably** → The loop is bounded at 4 rounds,
the tool set is small and whitelisted, arguments are schema-validated before any tool
runs, the user-visible text is produced by a constrained call rather than free
generation, and any failure falls back to today's behaviour. The blast radius is one
wrong sentence on a path that stores nothing.

**Several round trips against a 30s timeout** → Worst case is roughly 5 calls where the
product currently makes 1, so an advice answer will feel slower than a log confirmation.
The existing "responsiveness feedback" requirement (typing indicator) already covers the
user-facing half; the turn bound covers the tail.

**Tool output crowding the context** → Tools return aggregates, `list_food_entries` is
capped, and no tool returns raw ORM rows.

**Prompt injection aimed at the tool layer** → Identity is not expressible by the model,
every tool is read-only, and both existing guards remain. The worst achievable outcome
is a read of the user's own data phrased oddly.

**The `other` bucket is broad** → Routing all of `other` to the agent means greetings
also enter it. Mitigated by `used_data: false` in the answer schema and by a system
prompt that directs trivial messages to answer without any tool call, so a greeting
costs the gather phase one round and no retrieval.

**Scope creep toward writes** → The registry is read-only by construction in this
change. Adding a write tool must go through its own change, because it would need to
re-open `Only the storing path may confirm a record` and the clarification loop.

## Migration Plan

Additive and reversible. No migration, no schema change, no data backfill.

1. Extend `ScriptedLLM` to express `tool_calls` — nothing else is testable until this
   lands.
2. Add the agentic method to `LLMGateway` behind its own tests, unused in production.
3. Add the read-only tool registry, each tool tested directly against a seeded session.
4. Add the agent, then switch the `other` branch to it.

**Rollback**: route `other` back to `handle_other`. The agent and tool modules can stay
in the tree unused, since nothing else references them.

## Open Questions

- Whether the gather phase deserves a lower per-call timeout than the 30s global, since
  a stalled first round currently costs the whole budget. Tunable later without
  touching the specs.
- Whether `list_food_entries`' cap should be a count or a token estimate. A count is
  fine to start; only real transcripts will show whether it is the wrong axis.
- Whether the `report` intent should eventually route through the same tools so that
  reports and answers share one path. Deliberately out of scope: it would change
  observable report behaviour, so it belongs to its own change.
