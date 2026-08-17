# The advice agent

Answers open-ended questions about a user's own logged data - "come sto andando
questa settimana?", "posso permettermi una pizza stasera?", "mangio troppo tardi?" -
by reading the diary before replying, rather than answering from the model's general
knowledge. It is read-only: it cannot create, edit or delete anything. See
`openspec/changes/archive/2026-08-17-calobot-advice-agent/` for the full proposal,
design rationale and spec this implements.

## When it fires

`classify()` (`src/calobot/ingestion/classifier.py`) is unchanged: one flat,
schema-constrained call that still returns exactly one of `food | weight | activity |
correction | report | other`. The agent is invoked only when the intent is `other` -
`src/calobot/ingestion/pipeline.py`:

```python
else:
    reply = await advice_answer(
        self.session, self.gateway, self.user, self.tz,
        raw_text, content, self.settings.bot_label,
        self.settings.llm_advice_max_rounds,
    )
    messages.append(OutgoingMessage(text=reply))
```

Every other intent - a food log, a weight, an activity, a correction, a fixed report
- costs exactly what it cost before this feature existed. The agent never sits on the
hot path of logging something.

## Shape: gather, then narrate

Two calls, never one open-ended loop that both fetches data and writes the reply:

```
message ──► classify() ──"other"──► medical guard ──► GATHER ──► NARRATE ──► reply
                                          │                │          │
                                   is_medical_topic   call_agentic  call_structured
                                   (no model call)    (tool loop)   (AdviceAnswer)
```

1. **Gather** (`LLMGateway.call_agentic`, `src/calobot/llm/gateway.py`) - the model is
   offered a small, whitelisted set of read-only tools and may call some, all, or
   none of them, over up to `max_rounds` rounds. It cannot write anything in this
   phase; it can only ask for data.
2. **Narrate** (`LLMGateway.call_structured`) - one more call, with the accumulated
   tool results as its only input, constrained to the `AdviceAnswer` schema. This is
   the call that actually produces the Italian text the user reads.

The split matters: the *gather* phase runs unconstrained (tool-calling APIs don't
support `response_format` the way plain completions do), but the *narrate* phase runs
under the same JSON-schema-constrained decoding every other pipeline step uses. The
user-visible text is never free-form model output - it is always validated against a
schema before it is sent, and it is built only from data the tools actually returned.

```python
# src/calobot/advice/agent.py
class AdviceAnswer(BaseModel):
    answer_text: str
    used_data: bool            # False for a greeting or a how-to question
    declined_reason: str | None  # set when the data doesn't exist or isn't tracked
```

## The tool catalog

Every tool wraps a function that already backs a report or a chart, so an advice
answer for a period can never disagree with a report for the same period - neither
one is computed by the model. `user_id` and the timezone are closed over by
`build_tool_registry` (`src/calobot/advice/tools.py`) when the registry is built for
one message; they never appear in a tool's JSON schema, so the model has no way to
express, name or change whose data it's reading.

| Tool | Args | Wraps | Returns |
|---|---|---|---|
| `get_calorie_summary` | `period`, `reference_day?` | `build_food_report` | total, daily average, budget, difference |
| `get_weight_summary` | `period`, `reference_day?` | `build_weight_report` | start/end kg, change, projection |
| `get_dietician_review` | `period`, `reference_day?` | `build_dietitian_review` | the structured behavioural review (week+ only) |
| `list_food_entries` | `start_day`, `end_day` | `get_entries_in_range` | capped per-entry facts (description, grams, kcal, time) |
| `get_profile_and_budget` | *(none)* | profile + budget | daily budget, goal, calories remaining today |

`period` is one of `day | week | month | year`; `reference_day` is optional and lets
the model ask about a past period ("la settimana scorsa") rather than only the
current one - the aggregator still does every computation, so this only changes
*which* window is asked for, never how it's summed.

Every tool returns an explicit `no_data: true` marker (with the period or range it
looked at) instead of an empty or zero-filled structure, so "you logged nothing that
week" is distinguishable from "the tool didn't run". `list_food_entries` also caps at
`MAX_LISTED_ENTRIES` (50) and sets `truncated: true` past that, so a wide date range
can't crowd the narration call's context with raw rows.

## Worked example

**User:** "quante calorie ho mangiato oggi?"

**Gather round 1** - the model requests one tool call:

```json
{"name": "get_calorie_summary", "arguments": {"period": "day"}}
```

`_run_one_tool` validates `{"period": "day"}` against `PeriodQuery`, runs the
handler, and feeds the result back as the tool's response message:

```json
{
  "no_data": false,
  "period": "day",
  "reference_day": "2026-08-17",
  "total_kcal": 620,
  "daily_average_kcal": 620,
  "budget_kcal": 2100,
  "difference_kcal": -1480,
  "days_with_no_data": []
}
```

**Gather round 2** - the model requests no further tool call. `call_agentic` returns
`GatherResult(tool_results=[...], exhausted=False)`.

**Narrate** - one `call_structured` call with the tool result and the original
question, constrained to `AdviceAnswer`:

```json
{"answer_text": "Oggi hai mangiato circa 620 kcal, ben sotto il tuo budget di 2100.", "used_data": true, "declined_reason": null}
```

**Reply sent to the user:** *"Oggi hai mangiato circa 620 kcal, ben sotto il tuo
budget di 2100."*

A question needing no data ("ciao", "come funziona il bot?") skips the tool call
entirely - the gather round returns with no `tool_calls`, `gather.tool_results` is
empty, and narration answers directly with `used_data: false`.

## Safety guarantees

Two deterministic guards sandwich the agent, the same two that already sandwich the
plain conversational reply:

```python
# src/calobot/advice/agent.py
if is_medical_topic(raw_text):
    return REFUSAL_TEXT           # before ANY model call or tool call

...

if asserts_a_record(reply):
    return UNFOUNDED_CLAIM_REPLACEMENT   # after narration, before the user sees it
```

- **Medical guard** (`safety/medical.py`) - a keyword match that runs before the
  gather phase even starts. A clinical question triggers zero model calls and zero
  data retrieval.
- **False-confirmation guard** (`safety/claims.py`) - `asserts_a_record` now catches
  claims of *deletion or modification* as well as *creation* (`registrat`, `salvat`,
  `eliminat`, `cancellat`, `modificat`, `rimoss` stems), because the agent can
  plausibly be asked to "eliminate" or "change" something and must never claim it
  did. If the narrated reply trips this, it's replaced wholesale with
  `UNFOUNDED_CLAIM_REPLACEMENT` rather than edited - the reply was generated on a
  false premise, and trimming the offending sentence would leave text that's still
  wrong about what happened.
- **Read-only by construction** - there is no write tool in the registry. A request
  to delete an entry or change a goal can only ever be declined in the narrated text;
  it cannot be carried out, because the tool that would do it does not exist.
- **Identity is not a parameter** - see the tool catalog above. `test_advice_tools.py`
  pins this: `assert "user_id" not in schema_text` against every tool's
  `model_json_schema()`.

## Graceful failure

Nothing in this path raises an error to the user. Three distinct outcomes, each with
its own fixed message:

| Situation | What happens | Message |
|---|---|---|
| A tool's handler raises | `_run_one_tool` (`llm/gateway.py`) catches it, feeds the model a plain refusal string, no exception text or stack trace | (model still answers, likely `declined_reason` set) |
| The gather loop hits `max_rounds` without stopping | `GatherResult.exhausted = True` | `COULD_NOT_ANSWER_TEXT` |
| The LLM endpoint is unreachable, or narration fails validation | `LLMError` caught in `advice_answer` | falls back to `handle_other` (the old plain conversational reply) |

The last row is why rollback is a one-line change: if the agent ever needs to be
disabled, routing `other` back to `handle_other` directly reproduces exactly this
fallback path.

## Configuration

```bash
CALOBOT_LLM_ADVICE_MAX_ROUNDS=4   # default; bounds the gather phase
```

The gather and narrate steps are named `advice_gather` and `advice_narrate`
respectively (the `step` argument to `call_agentic`/`call_structured`). `Settings.
model_for_step` / `temperature_for_step` only recognise per-step overrides for
`classify` and `extract` today - `CALOBOT_LLM_ADVICE_GATHER_MODEL` and similar do not
exist yet. Both advice steps run on the global `CALOBOT_LLM_MODEL` /
`CALOBOT_LLM_TEMPERATURE`. Adding per-step overrides would mean extending those two
dict literals in `settings.py`, following the existing `classify`/`extract` pattern.

## Telemetry

Every model call in one advice interaction - every gather round plus the narration
call - carries the same `agent_turn_id` (a `uuid4().hex` minted once per
`call_agentic` invocation), plus a `round_index` and, on a gather round, the
`tool_name`(s) requested. This is threaded into `call_structured`'s narration call
via its `extra_telemetry` parameter:

```python
result = await gateway.call_structured(
    ..., extra_telemetry={
        "agent_turn_id": gather.agent_turn_id,
        "round_index": "narrate",
        "tool_name": None,
    },
)
```

Without it, the real-time monitor and activity export would show four or five
unexplained `llm_transaction` events per advice message with no way to tell they
belong together. The fields are additive (`.get(...)`-based in
`telemetry/server.py`), so nothing that doesn't know about them breaks.

## Extending: adding a new tool

1. Write a Pydantic args model (flat - no nested/union fields, same rule as every
   other LLM-facing schema in this codebase) and an async handler in
   `src/calobot/advice/tools.py`. The handler takes the validated args model and
   returns a JSON-serializable `dict`, with an explicit `no_data` key on the empty
   path.
2. Wrap it in a `ToolDefinition` and append it to the list `build_tool_registry`
   returns. Do not add `user_id` (or anything that identifies a user) to the args
   model - close over it instead, the way every existing handler does.
3. If it wraps a new aggregator, that aggregator should already be deterministic and
   already used by the report/chart path - if it isn't, write that first. The agent
   selects data; it never computes it.
4. Add a direct test in `tests/test_advice_tools.py` (seed data, call
   `build_tool_registry(...)`, call `tools[name].handler(args)` directly, assert on
   the returned dict - no LLM involved) and a behavioural test in
   `tests/test_advice_behaviour.py` if the tool changes what a user-facing scenario
   can do.

A write tool is deliberately not on this list. Adding one means re-opening `Only the
storing path may confirm a record` and the clarification loop (`specs/message-
ingestion`), and belongs to its own change, not an extension of this one.

## Testing patterns

**Staging a full agent turn** - `tests/harness/llm.py`'s `ScriptedLLM` can express
tool-calling rounds, not just content-only responses:

```python
from harness.llm import ToolCall

llm.push_agent_turn(
    [[ToolCall(name="get_calorie_summary", arguments={"period": "day"})]],
    final={"answer_text": "Oggi hai mangiato 620 kcal.", "used_data": True, "declined_reason": None},
)
```

This stages one gather round requesting `get_calorie_summary`, followed
automatically by a `NoMoreToolCalls` signal ending the gather loop, then the
narration payload. For a question needing no data, pass an empty list of rounds:

```python
llm.push_agent_turn([], final={"answer_text": "Ciao!", "used_data": False, "declined_reason": None})
```

To stage an exhausted round bound, push raw `ToolCallsResponse`s directly (no
`NoMoreToolCalls`, so the loop never sees a stopping signal) up to `max_rounds` times:

```python
from harness.llm import ToolCallsResponse

for _ in range(settings.llm_advice_max_rounds):
    llm.push(ToolCallsResponse(calls=[ToolCall(name="get_calorie_summary", arguments={"period": "day"})]))
```

**Three test layers**, each answering a different question:

- `tests/test_advice_tools.py` - does one tool's handler compute the right thing
  against a seeded database? No LLM involved.
- `tests/test_advice_agent.py` - does the gather/narrate/guard wiring behave
  correctly in isolation, given scripted model responses? Calls `advice.agent.answer`
  directly.
- `tests/test_advice_behaviour.py` - does the whole thing work end-to-end through the
  real Telegram dispatcher (`tests/harness/client.py`), one test per scenario in
  `specs/advice-agent`? This is the layer that would catch a regression a user could
  actually hit.

## What's out of scope

- **Writing anything.** No tool creates, edits or deletes an entry, changes a goal,
  or touches the profile. See "Safety guarantees" above.
- **Macronutrients, sodium, sugar, or anything else the product doesn't track.** The
  gather prompt tells the model this explicitly; there is no tool for it, so there is
  nothing to hallucinate a number from.
- **Conversational memory.** The agent is stateless per message - it has no
  cross-turn memory beyond what `raw_text` and the tool results carry in one
  invocation.
- **Routing every message through tools.** `classify()` stays a single flat call;
  only `other` reaches the agent. A food log still costs exactly one `classify` call
  plus one `extract` call, as it always did.
