## Context

Three surfaces currently emit advice and remember none of it: `build_dietitian_review`
and `build_daily_advice` in `calobot.reporting.dietician` (pure LLM calls with no
`session`/`user`), and `calobot.advice.agent.answer`'s meal-suggestion path, which
already derives a deterministic `_DerivedSuggestion` (mode, ceiling, remaining) before
composing the reply. No-retention mode is already enforced once, centrally, at the
session layer: `NonRetentiveAsyncSession.commit` (`persistence/engine.py`) turns a
commit into a no-op flush whenever `active_no_retention` is set, so every write made
through the request-scoped session is already covered without a per-call check.
`hard_delete_user` (`persistence/repository.py`) is the one place that deletes rows
directly rather than soft-deleting, and is what `/cancellami` calls.

## Goals / Non-Goals

**Goals:**
- One new table, written from the three emission sites, read by one new advice-agent
  tool.
- A deterministic, code-driven outcome check for exactly two topics (meal timing,
  logging consistency), reusing `advice-longitudinal-signals`' aggregation signals so
  the same "before vs after" arithmetic that answers "sto migliorando?" also answers
  "did this suggestion work?".
- Verbatim-repeat suppression for the two report-attached actionable tips (dietician
  review, daily advice) via a prompt instruction, not a hard filter on model output.

**Non-Goals:**
- No change to advice wording/quality beyond suppressing exact repetition.
- No unprompted message (`proactive-nudges`'s job).
- No outcome check for topics other than meal timing and logging consistency — advice
  that doesn't match either stays permanently undetermined, which is a correct answer,
  not a gap to fill later with a broader classifier.

## Decisions

**A single deterministic keyword classifier decides a record's `topic`, run once at
write time, not re-run on read.** The recording code (not the model) scans the
advice's own Italian text for markers of "eat earlier" vs "log more consistently"
(e.g. *presto/prima di sera/tardi* for timing; *registra/tieni traccia/ogni giorno*
for consistency) and stores the result as `topic: meal_timing | logging_consistency |
None`. This is deterministic code operating on stored text, not the model reporting on
itself — the distinction the `advice-agent` "read-only tools" requirement draws is
between the model claiming a fact and code establishing one; a regex over already-
produced text is the latter. Classifying at write time, once, means outcome
resolution later never has to re-derive what the advice was "about" — it already
knows. A record whose text matches neither pattern gets `topic: None` and never enters
outcome resolution, matching the "no matching signal" requirement scenario exactly.

**Outcome resolution runs lazily, on read, not on a schedule.** There is no
`background-scheduler` yet (a sibling, independent change), so nothing periodic exists
to sweep unresolved records. Instead, `resolve_pending_outcomes(session, user, tz)` is
called at the two points something reads advice records: before the read-only advice
tool answers, and before a new report-attached tip is composed (which needs to know
the prior tip's outcome for suppression anyway). It walks topic-tagged, still-
undetermined records at least `MIN_DAYS_FOR_SIGNAL` days old (reusing the constant
`advice-longitudinal-signals` introduced in `calobot.reporting.aggregation`, so "enough
data to mean something" is one definition, not two), computes the relevant signal for
the days after the record against the days before it via
`calobot.reporting.aggregation` helpers, and persists whichever outcome it settles on
(or leaves it undetermined if the after-window itself doesn't clear the bar yet).
Recomputing on every read is cheap (one aggregation query) and self-healing: a
record's outcome can only move from undetermined to decided, never flip once decided,
so re-running it is idempotent.

**Meal-timing outcome direction: "moved earlier" counts as followed.** Every timing
tip this codebase's prompts produce nudges toward eating earlier / more regularly
(`DIETICIAN_SYSTEM_PROMPT`'s "pattern di fame notturna", `DAILY_ADVICE_SYSTEM_PROMPT`'s
rest-of-day framing) — there is no prompt path that would tell a user to eat *later*.
A fixed direction (earlier = followed) is therefore sound without needing to parse
which direction a specific tip argued for. If a future tip ever argued the opposite,
this would need revisiting, but nothing in the current prompts does.

**Suppression is a prompt instruction, not a hard filter on the LLM's output.**
"Not repeated verbatim" is enforced by handing the previous unresolved tip's exact
text to the system prompt with an explicit instruction not to reproduce it, the same
way other qualitative constraints in `DIETICIAN_SYSTEM_PROMPT`/`DAILY_ADVICE_SYSTEM_PROMPT`
already work (e.g. "never state a gram amount"). A hard post-hoc string-equality check
would only catch exact matches and do nothing for a near-verbatim rewording, while
telling the model what it already said and asking it not to repeat it addresses the
actual failure mode (repeating the same tip because it wasn't told otherwise).

**Recording happens at the call sites in `ingestion/pipeline.py` and
`advice/agent.py`, not inside `calobot.reporting.dietician`.** The dietician module's
two builder functions are pure LLM wrappers with no `session`/`user`/`tz` triple to
write with; threading persistence through them would mix "compose text" with "persist
a fact" in one function. Both builders gain one new optional parameter,
`avoid_repeating: str | None`, so the suppression instruction can be composed without
either function needing to know how or where the previous tip was fetched from.

**The new table's schema mirrors `FoodEntry`/`ActivityEntry`'s soft-delete
convention (`deleted_at`) even though nothing sets it yet.** The proposal calls this
out explicitly ("soft-delete conventions apply to it as they do to entries"); every
read path filters it the same way `get_entries_in_range` already does, so a future
feature that needs to retract a single advice record (not the whole account) has
somewhere to write without a schema change. `/cancellami` still hard-deletes it, via
`hard_delete_user`, exactly like every other table.

## Risks / Trade-offs

- **A regex classifier over LLM-authored Italian is heuristic and will miss
  paraphrases.** Acceptable because a miss only means a record's topic stays `None`
  (outcome stays undetermined forever) — the failure mode is "less signal", never a
  wrong signal, which is exactly the "advice with no matching signal" scenario the
  spec already treats as a normal outcome, not an error.
- **Outcome resolution re-runs an aggregation query on every relevant read.** With one
  user per request and a handful of undetermined records at a time, this is one or two
  extra `get_entries_in_range` calls per advice-tool invocation — negligible next to
  the LLM round trip already dominating that path.
