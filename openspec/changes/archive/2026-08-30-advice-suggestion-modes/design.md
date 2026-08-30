## Context

See `proposal.md` — Why, for the motivation.

The advice agent runs a two-phase shape (gather → narrate) established in the original
`calobot-advice-agent` change: a bounded tool-calling loop that only retrieves, then
one `call_structured` that turns retrieved results into user-visible text. Constraints
that shape this design:

- The gateway degrades on nested or union schemas (`CLAUDE.md`), so the response model
  must stay flat.
- Every tool wraps a deterministic aggregator that already backs a report, so an
  advice answer cannot disagree with a report for the same period.
- `user_id` and `tz` are closed over by `build_tool_registry` and never appear in a
  tool's args schema.
- Tests use a stubbed gateway, so any requirement whose enforcement lives in a prompt
  is unobservable to the suite.
- The agent already has one precedent for deterministically guarding model output:
  `asserts_a_record` suppresses an answer that claims a write and substitutes
  `UNFOUNDED_CLAIM_REPLACEMENT`.

## Goals / Non-Goals

**Goals:**

- Make the positive/negative budget branch a Python decision, computed once, from a
  figure the code already has.
- Make the prescriptive requirements assertable without invoking a real model.
- Keep the narration prompt's growth linear in the number of modes rather than
  accumulating in one shared string.
- Leave the user-visible answer shape unchanged for the paths that work today.

**Non-Goals:**

- Longitudinal or continuity depth (advice memory, follow-through, "what changed"
  tools). Explicitly deferred; this change is the structural prerequisite, not the
  feature.
- Any change to classification or routing. The intent stays `other`.
- Deterministic calorie lookup for suggested dishes against the bundled food database.
  Considered and rejected below.
- Proactive or unprompted messages.

## Decisions

### Decision 1: Detection is a tool call, not a post-hoc code heuristic

A new read-only tool `get_meal_suggestion_context` (no args) is added. The model calls
it when it judges the user is asking what to eat. That call *is* the detection.

The handler computes, deterministically, from the same `current_budget` +
`build_food_report` + `build_activity_report` path `_profile_and_budget_handler`
already uses:

```
remaining = round(target_kcal + activity_credit_kcal - eaten_today)

budget is None            -> mode = "no_budget",     ceiling_kcal = None
remaining > 0             -> mode = "within_budget", ceiling_kcal = remaining
remaining <= 0            -> mode = "over_budget",   ceiling_kcal = OVER_BUDGET_CEILING (100)
```

It also returns the recent food descriptions the qualitative-variety reasoning needs,
so one tool call replaces the two the prompt currently begs for.

*Why over the alternatives:*

- **Post-hoc code detection** (inspect `raw_text` after gathering, fetch budget if it
  looks prescriptive) requires keyword-matching free-form Italian. Brittle, and it
  puts a language judgement in code — exactly the wrong side of the split this
  codebase maintains everywhere else.
- **A new `meal_suggestion` classifier intent** makes routing explicit and testable
  upstream, but widens the change into `message-ingestion` and the classifier, where
  the intent boundary has been churning across three of the last five archived
  changes. Not worth coupling this refactor to that.
- **Leaving `GATHER_SYSTEM_PROMPT` as-is** and deriving mode only when
  `get_profile_and_budget` happens to appear in the results keeps the "usa SEMPRE two
  tools" fragility: two independent instructions the model must both honour.

The chosen shape puts the language judgement in the model (one decision: call the tool
or not) and the arithmetic branch in Python (all remaining decisions).

`get_profile_and_budget` is retained unchanged — it answers non-prescriptive budget
questions ("quante calorie mi restano?"), which should not select a suggestion prompt
fragment.

### Decision 2: The narration prompt is composed, not branched

`_narrate_system_prompt(bot_label)` becomes
`_narrate_system_prompt(bot_label, mode)`: a base prompt plus exactly one mode
fragment appended, selected in Python from the mode present in the tool results. When
no `get_meal_suggestion_context` result is present, no fragment is appended and the
prompt is the base — today's non-prescriptive behaviour.

This is what makes the requirements testable. A test seeds a user 150 kcal over
budget, runs the turn, and asserts that the `over_budget` fragment was the one sent to
the gateway — an assertion about code, not about a stubbed answer string.

The union deliberately lives in prompt *selection* rather than in the response schema,
so the schema stays flat and the gateway constraint is respected.

### Decision 3: `AdviceAnswer` gains flat observability fields

```
suggestion_mode: Literal["none", "within_budget", "over_budget", "no_budget"] = "none"
suggested_kcal_total: int | None = None
```

Both are self-declarations by the model about the answer it wrote, defaulted so that
non-prescriptive answers are unaffected. `suggested_kcal_total` is the model's
estimate of the dish it proposed — permitted under Decision 5, and the input the guard
checks.

Rejected: modelling each mode as its own response schema and picking at call time.
That is a union in all but name, triples the schema surface, and buys nothing the
composed prompt does not already give.

### Decision 4: A deterministic guard on the narrated answer

A new guard runs after narration, alongside `asserts_a_record`, and suppresses the
answer when:

- `result.suggestion_mode` disagrees with the mode the tool derived — the model
  narrated a different situation than the one the data describes; or
- mode is `over_budget` and `suggested_kcal_total` exceeds `ceiling_kcal`.

On suppression the reply is a deterministic per-mode fallback text rather than the
generic `UNFOUNDED_CLAIM_REPLACEMENT`, because the user asked a legitimate question
and a confused meta-reply serves them worse than a plain safe suggestion. The
suppression is logged at warning level, as `asserts_a_record` does.

*Honest limitation:* the guard checks what the model *declared*, not what it actually
wrote. A model that proposes a 400 kcal dish and declares `50` defeats it. This is
strictly better than the status quo (which checks nothing) and is the same trust
boundary `used_data` already sits on; closing it fully would need the deterministic
lookup rejected in Decision 6.

### Decision 5: Determinism is scoped to figures about logged data

The `advice-agent` requirement "Reported figures come from deterministic computation"
is amended to apply to figures **about the user's logged food, weight and activity**.
A separate, explicit carve-out covers figures about a hypothetical not-yet-eaten dish:

- they are model estimates, and the answer must frame them as approximate;
- they are never stored;
- they are never presented as, or arithmetically combined with, a logged total or a
  computed budget in a way that implies equivalence.

This resolves a contradiction that is live in the spec today, not one this change
introduces: the determinism requirement forbids the model from computing a presented
figure, while the meal-suggestion requirement asks it to propose dishes "whose
estimated calories do not exceed the remaining balance". The bot has been producing
such estimates all along; the spec simply did not admit it.

### Decision 6: Suggested-dish calories are not looked up against the bundled data

Estimating a proposed dish from the bundled CC0 food data would make even suggestion
figures deterministic. Rejected for now: it requires resolving free-form generated
dish names against the dataset, is bounded by what the CC0 sources actually cover
(`DATA_SOURCES.md` — CREA and the Compendium were deliberately excluded), and turns a
prompt refactor into a data-matching project. Decision 5 makes the current behaviour
honest instead; this remains open as a later change.

## Risks / Trade-offs

- **The model never calls `get_meal_suggestion_context`** → mode is `none`, no
  fragment is appended, and the answer degrades to today's generic behaviour rather
  than to an error. Mitigated by a specific tool description and by the fact that this
  failure mode is no worse than the current "usa SEMPRE" instruction being ignored.

- **Two tools both surface budget data** (`get_profile_and_budget` and the new one)
  → the model may call the wrong one for a prescriptive question, yielding mode
  `none`. Mitigated by descriptions that separate "quante calorie restano" from "cosa
  posso mangiare"; accepted as the cost of not disturbing the non-prescriptive path.

- **Guard false positives** suppress a good answer → the user gets a safe but blander
  deterministic reply. Preferred over the inverse, and the warning log makes the rate
  observable.

- **The guard trusts a self-declared figure** → see Decision 4. Documented rather than
  hidden.

- **`OVER_BUDGET_CEILING` as a constant** encodes a nutrition judgement (100 kcal) in
  code where it was previously in prose. This is the point — it becomes reviewable and
  changeable in one place — but it does harden a number that was soft.

## Migration Plan

No data migration. The change is confined to `src/calobot/advice/` and its tests;
rollback is a revert. Behaviour for users with an incomplete profile (`no_budget`) and
for all non-prescriptive questions is unchanged by construction.

## Open Questions

- Whether `no_budget` deserves its own prompt fragment (nudging the user to complete
  onboarding) or should fall through to the base prompt. Either can be chosen during
  implementation without affecting the specs or the task breakdown.
