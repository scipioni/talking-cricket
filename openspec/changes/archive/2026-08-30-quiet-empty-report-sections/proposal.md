## Why

A report request without a stated topic defaults to `topic="all"`, which runs three
independent sections — calories, weight, activity. Each empty section emits its own
standalone message, so a user who logs food but not weight or activity gets their
calorie report followed by two bureaucratic lines:

> Non ci sono dati sul peso per questo periodo.
> Non ci sono dati sull'attività per questo periodo.

They did not ask about weight or activity. They asked for a report. Being told twice
that data they never logged is missing is noise, and it arrives on every single report
for any user who does not log all three kinds of entry — which is most of them.

The asymmetry is also visible: the empty **food** section already gets a warm
conversational response (from `conversational-empty-reports`), while weight and activity
get flat hardcoded strings that change never touched.

## What Changes

- When the user did not ask about a specific topic, an empty weight or activity section
  produces no message at all. The report shows what there is.
- When the user *did* ask about that topic specifically ("come va il peso?"), an empty
  result still says so — that is a direct question deserving a direct answer, and
  silence would read as a failure.
- Unchanged: a period with nothing logged at all still produces the existing
  conversational empty-diary response. Because the calorie section always runs for an
  unscoped request, a report can never fall silent.

**Non-goals:** no change to what a non-empty report contains, no change to the
conversational empty-food response, no change to charts or the dietician review.

## Capabilities

### Modified Capabilities

- `reporting`: gains a requirement distinguishing a report the user scoped to one topic
  from an unscoped one, and stating that an unscoped report reports only the topics that
  have data, while a scoped one reports the absence.

## Impact

- `src/calobot/ingestion/pipeline.py` — the weight and activity branches of the report
  path.
- `tests/` — new coverage for both directions; there is currently **no test asserting
  either message**, which is why the noise went unnoticed.
- No database schema change, no migration, no new dependency, no additional LLM call —
  this removes messages rather than generating them.
