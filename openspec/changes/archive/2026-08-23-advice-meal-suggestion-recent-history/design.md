## Context

`list_food_entries` (`src/calobot/advice/tools.py`) already exists as a
read-only tool, but its `DateRangeQuery` args require the model to supply
exact ISO `start_day`/`end_day` values. Nothing in `GATHER_SYSTEM_PROMPT` or
the message content currently tells the model what today's date is, and no
existing test exercises `list_food_entries` end-to-end through the LLM (only
via a direct handler call in `test_advice_tools.py`) - so there is no
established, verified pattern in this codebase for the model reliably
producing absolute dates. Every other period-based tool (`get_calorie_summary`,
`get_weight_summary`, `get_dietician_review`) instead takes a `period`
literal and an optional `reference_day`, resolved server-side via
`_resolve_reference_day`/`today_in_timezone`, and defaults to today when the
model omits `reference_day` entirely. See proposal.md - Why for the
motivating gap.

## Goals / Non-Goals

**Goals:**
- Give the meal-suggestion path a recent-eating signal without relying on the
  model to compute absolute dates.
- Reuse the existing qualitative, description-based reasoning style (no
  macronutrient grams stated) already established by the dietician review and
  the day-report advice.

**Non-Goals:**
- Extending `list_food_entries` itself to accept relative days - it is used
  elsewhere for explicit-range questions ("cosa ho mangiato tra il 3 e il 5?")
  and changing its contract is out of scope.
- Any new database query pattern - `get_recent_food_descriptions` is a thin
  wrapper around the same `get_entries_in_range` repository function every
  other tool already uses.

## Decisions

**New tool `get_recent_food_descriptions(days: int = 2)` instead of reusing
`list_food_entries`.** `days` is a small bounded int (validated 1-5, default
2) rather than a date range; the handler computes
`[today - days, today + 1)` server-side via `today_in_timezone(tz)`, exactly
like `_resolve_reference_day` does for the period tools. This sidesteps the
date-computation risk described in Context, and keeps the tool's only
degree of freedom (how far back to look) something a small validated int
handles safely regardless of what the model passes.
- Why not just always look back a fixed 2 days with no parameter: kept the
  `days` argument because a future caller (or the model, for "cosa ho
  mangiato negli ultimi giorni?") may reasonably want a slightly different
  window; defaulting to 2 keeps today's behavior change minimal to reason
  about.
- Why 2 days as the default: matches "questa sera" / "cosa mangio dopo"
  framing - the point is recent short-term pattern (yesterday and today), not
  a weekly trend, which `get_dietician_review` already covers for periods of
  a week or longer.

**Prompt wiring:** `GATHER_SYSTEM_PROMPT` gets one added bullet instructing
the model to also call `get_recent_food_descriptions` for meal/recipe
questions; the `RICETTE E SUGGERIMENTI DI PASTI` block in
`_narrate_system_prompt` gets an added paragraph telling the model to look at
those descriptions the same way the dietician review's density insight
does (high/low density, apparent absence of a protein-ish food), and
restating the existing "never state a macronutrient gram amount" rule so it
is not lost when the new instruction is added.

## Risks / Trade-offs

- [Model still drifts into stating a specific gram amount despite the
  restated rule] → same mitigation as the other two changes in this area
  (`budget-include-activity-kcal`): the rule is restated, not introduced for
  the first time, and covered by a test asserting no digit-plus-"g" pattern
  near a macronutrient word in a stubbed narration fixture.
- [Two similar-looking "recent food" tools now exist - `list_food_entries`
  (explicit range) and `get_recent_food_descriptions` (relative days) - risk
  of the model picking the wrong one] → their descriptions in the tool
  registry are kept clearly distinct ("intervallo di date preciso" vs
  "ultimi N giorni da oggi"), and `GATHER_SYSTEM_PROMPT` names
  `get_recent_food_descriptions` explicitly for the meal-suggestion case.
