## 1. Test harness prerequisite

Nothing below is testable until `ScriptedLLM` can express tool calls
(`design.md` — Migration Plan step 1).

- [x] 1.1 Extend `tests/harness/llm.py` so a staged payload can represent an assistant
      message carrying `tool_calls` (id, function name, JSON arguments) in addition to
      today's content-only payload, keeping interception at the OpenAI client so the
      real gateway still runs
- [x] 1.2 Make `ScriptedLLM.calls` record the `tools` argument each call was made with,
      so a test can assert which tools were offered to the model
- [x] 1.3 Add a helper for staging a whole agent turn (N tool-call rounds followed by a
      final narration payload) so scenario tests stay readable
- [x] 1.4 Confirm the existing suite still passes unchanged with the extended stub

## 2. Agentic gateway call

- [x] 2.1 Add an agentic method to `LLMGateway` that passes `tools` to the same
      OpenAI-compatible endpoint and returns the model's requested tool calls or its
      signal that it has enough data
- [x] 2.2 Validate model-supplied tool arguments against that tool's schema before
      running it; on failure feed the rejection back to the model and do not run the
      tool (`specs/message-ingestion` — Invalid retrieval arguments from the model)
- [x] 2.3 Refuse a request for a tool that is not in the offered set, feeding the
      refusal back rather than raising
- [x] 2.4 Bound the loop at a configurable number of rounds (default 4) and return a
      distinct exhausted-bound outcome rather than an answer
- [x] 2.5 Map transport and status failures onto the existing typed errors from
      `llm/errors.py`, as `call_structured` does
- [x] 2.6 Add a `CALOBOT_`-prefixed setting for the round bound, following the existing
      per-step settings pattern
- [x] 2.7 Unit-test 2.1-2.5 directly against `ScriptedLLM`, including a round that
      requests an unknown tool and a round with invalid arguments

## 3. Read-only tool registry

- [x] 3.1 Create the tool registry module, built per message, with `user_id` and the
      timezone closed over at construction and absent from every exposed JSON schema
      (`specs/advice-agent` — User identity is bound outside the conversation)
- [x] 3.2 Implement `get_calorie_summary` over `build_food_report` (named
      `build_calorie_report` in design.md; `build_food_report` is the actual
      function)
- [x] 3.3 Implement `get_weight_summary` over `build_weight_report`
- [x] 3.4 Implement `get_dietician_review` over `build_dietitian_review`, rejecting
      periods shorter than a week (`specs/dietician-reviews` — Question about a period
      shorter than a week)
- [x] 3.5 Implement `list_food_entries` over `get_entries_in_range`, returning capped
      compact per-entry facts and never raw ORM rows
- [x] 3.6 Implement `get_profile_and_budget` returning the daily budget, goal and
      today's remaining budget
- [x] 3.7 Give every tool an explicit `no_data` marker naming the period it examined, so
      "logged nothing" is distinguishable from a failed tool
      (`specs/advice-agent` — Absent data is reported as absent, not estimated)
- [x] 3.8 Verify every tool filters `deleted_at` and takes the timezone as a parameter,
      per the project conventions
- [x] 3.9 Test each tool directly against a seeded in-memory session, including its
      empty-period behaviour
- [x] 3.10 Add a test asserting no tool's exposed schema contains a user identifier

## 4. The advice agent

- [x] 4.1 Create the agent module with the two-phase flow from `design.md` — Decision 3:
      a bounded gather loop, then one `call_structured` narration call
- [x] 4.2 Define the flat `AdviceAnswer` schema (`answer_text`, `used_data`,
      `declined_reason`)
- [x] 4.3 Write the Italian system prompt for the gather phase: what the bot does and
      does not track, that totals come from the summary tools rather than arithmetic,
      and that a trivial message needs no tool call
- [x] 4.4 Write the Italian system prompt for the narration phase, in the established
      voice, forbidding any figure not present in the supplied tool results
- [x] 4.5 Run `is_medical_topic` before the gather loop so a clinical message reaches
      neither the model nor any retrieval (`specs/advice-agent` — Existing safety limits
      apply to the agent)
- [x] 4.6 Run `asserts_a_record` on `answer_text` and replace a violating answer
      wholesale, as `handle_other` does
- [x] 4.7 Fall back to `handle_other` on an exhausted bound, a loop error or a failed
      narration call (`design.md` — Decision 7)
- [x] 4.8 Set `declined_reason` and suppress invented figures when tools report
      `no_data`, rather than answering from an adjacent period (enforced by the
      narration prompt; `_run_one_tool` in `llm/gateway.py` was also extended to
      catch a tool handler's own exceptions and feed back a plain refusal, covering
      `specs/advice-agent` — "A retrieval fails", discovered while wiring this up)

## 5. Pipeline wiring

- [x] 5.1 Route the `other` branch in `ingestion/pipeline.py` to the advice agent,
      passing the session, gateway, authenticated user and `self.tz`
- [x] 5.2 Confirm `classify()` is untouched and still one flat call, and that the food,
      weight, activity, correction and report paths are byte-for-byte unchanged
- [x] 5.3 Confirm a message carrying a loggable intent still reaches the logging path
      and never the agent (`specs/message-ingestion` — A message carrying a loggable
      intent is not conversation) — covered by the existing
      `test_the_contradiction_routes_the_message_to_the_log`

## 6. Telemetry

- [x] 6.1 Add a shared `agent_turn_id`, round index and originating tool name to the
      `llm_transaction` events emitted during one agent turn
      (`design.md` — Decision 8)
- [x] 6.2 Confirm `realtime-monitor` and `activity-export` still render and export
      correctly with the added fields, and that existing consumers are unaffected

## 7. Behavioural tests

One test per spec scenario, driven end-to-end through the transport double.

- [x] 7.1 Question about the user's own eating retrieves the period and answers from its
      real totals
- [x] 7.2 Comparison question retrieves both periods
- [x] 7.3 Greeting is answered with no retrieval and `used_data: false`
- [x] 7.4 A stated total matches what a report for the same period reports
- [x] 7.5 Question about macronutrients is declined as untracked, with no estimate
- [x] 7.6 Question about an empty period says there is no data for it
- [x] 7.7 Question needing a pattern over too few logged days declines instead of
      asserting one
- [x] 7.8 A message naming another user reads only the sender's own data
- [x] 7.9 A message instructing the agent to switch user or act as admin has no effect
- [x] 7.10 A request to delete an entry or change a goal is neither performed nor
      claimed
- [x] 7.11 An answer asserting a record was made is suppressed and replaced
- [x] 7.12 Exhausted round bound produces the invite-to-rephrase reply, not a partial
      answer
- [x] 7.13 A failing tool produces a plain message with no internal error text
- [x] 7.14 A medical question is refused with no model call and no retrieval
- [x] 7.15 Assert the advice path creates no `FoodEntry`, `WeightEntry` or
      `ActivityEntry` and mutates no profile row

## 8. Simulation and checks

- [x] 8.1 Add an advice exchange to the simulation harness scenarios so the agent is
      covered by a simulated multi-day conversation (a new `NothingStored` step in
      `marco_three_days()`, day one, "straight" behaviour — exercised live by
      `test_live_simulation.py`, structurally checked offline)
- [x] 8.2 Run `task check` (test, lint, typecheck) and resolve anything this change
      introduced (the remaining lint errors, one mypy error and one test failure are
      pre-existing and unrelated — verified via `git stash`)
- [x] 8.3 Update `docs/README-technical.md` with the advice path and its bounds

## 9. Spec sync

- [x] 9.1 Run `openspec validate calobot-advice-agent --strict`
- [x] 9.2 Confirm the delta for `message-ingestion` still matches the current main spec
      text before archiving, since that spec has changed recently
