## Context

See `proposal.md` — Why for motivation, and `specs/dietician-reviews/spec.md` for requirements.

This design runs on top of the established `calobot-v1` core and `calobot-photo-input` pipelines. Two existing systems carry the weight:
1. `LLMGateway` which handles structured openai-compatible calls with automatic schema validation and JSON retries.
2. `get_entries_in_range` which queries user food logs based on UTC boundaries converted from the local timezone (`Europe/Rome`).

## Goals / Non-Goals

**Goals:**
- Provide highly personalized behavioral nutritional guidance in Italian.
- Deliver the review alongside the standard calorie chart in Telegram for reports of a week or longer.
- Keep the database schema and storage completely unchanged by deriving nutritional quality indirectly from calorie density, timing, and provenance.

**Non-Goals:**
- Tracking or estimating protein, carbs, or fats. Calobot is a calorie-focused tracker; tracking macros would require extensive database migrations and violate the simplicity model.
- Pre-computing reviews via CRON or background workers. Reviews are computed dynamically at report-request time.

## Decisions

### 1. Leverage `LLMGateway.call_structured` with a Pydantic schema

To ensure absolute reliability, safety, and consistent formatting, the dietician review is generated as a structured Pydantic model (`DieticianReview`) rather than unstructured Markdown. 

```python
class DieticianReview(BaseModel):
    summary: str
    density_insight: str
    temporal_pattern_insight: str
    sourcing_insight: str
    actionable_tip: str
```

**Rationale**: Unstructured LLM outputs suffer from text formatting drift, hallucinated data, and length variance. By enforcing a JSON schema, we ensure the bot always returns the exact sections we need, which can be cleanly formatted as unified Telegram Markdown.

**Alternatives considered**: Unstructured markdown completion. Rejected because it lacks schema validation, making it prone to breaking the Telegram markdown parser or exceeding character count budgets.

### 2. Extract indirect nutritional signals instead of tracking macronutrients

Because Calobot does not store protein, carbs, or fat, we feed the LLM a structured history of indirect nutrition signals computed from the database:

- **Calorie Density**: Computed for each entry as `(kcal / grams) * 100` to yield kcal/100g. We categorize items as Low Density (<100 kcal/100g, promoting satiety) or High Density (>300 kcal/100g, low satiety).
- **Temporal Patterns**: Extracting the hour of day from `consumed_at.astimezone(tz)` to analyze meal intervals, late-night eating, or frontloading.
- **Sourcing Provenance**: Reporting the percentage of entries logged via high-trust sources (`etichetta` or `off`) vs estimates (`tabella` or `llm`).
- **Variety**: Counting and list-summarizing unique food descriptions.

**Rationale**: These signals are highly correlated with behavioral nutritional health. Instructing the clinical LLM to analyze these specific parameters yields deep, personalized behavioral insights without any database schema bloat.

**Alternatives considered**: Introduce macro tracking tables. Rejected because it requires major schema changes, migrations, and complex backfills.

### 3. Fetch and Generate Review Dynamically at Report-Time

When a user requests a weekly or monthly report, the pipeline:
1. Queries all food entries for the period.
2. Prepares the standard calorie figures and daily breakdown.
3. Renders the calorie chart.
4. Concurrently compiles a light, structured JSON summary of the entries (description, grams, kcal_per_100g, consumed hour, and provenance) and calls the LLM gateway.
5. Appends the formatted dietician text blocks below the calorie chart.

**Rationale**: Since Qwen3-VL/LLM is self-hosted with no token/cost limits, running on-demand reports is highly efficient and eliminates the complexity of background queuing and synchronization. The latency is entirely covered by the active Telegram typing indicator.

**Alternatives considered**: Nightly pre-computation. Rejected due to complex synchronizations required when a user adds, corrects, or deletes historical entries retrospectively.

### 4. Require a minimum data volume for clinical review

To prevent the dietician from giving generic advice, a review is only triggered if the user has logged food on **at least 3 distinct days** in the requested period. 

**Rationale**: A dietician cannot draw behavioral or timing conclusions from a single logged meal. Under 3 days, a friendly fallback message is returned:
*"Per darti un parere nutrizionale personalizzato ho bisogno di almeno 3 giorni di registrazioni in questo periodo. Continua così e presto avrò abbastanza dati per aiutarti!"*

## Risks / Trade-offs

- **[Risk] Latency increases food report wait time** → *Mitigation*: The typing indicator covers the entire pipeline. Additionally, the LLM call is bypassed entirely if the user does not have enough logged days, or if the report is for a single "day".
- **[Risk] LLM hallucinates macronutrient recommendations** → *Mitigation*: The system prompt explicitly forbids talking about grams of carbs/fats/proteins, instructing the LLM to restrict its clinical critique to volumetric satiety (calorie density), meal timing, and logging precision.
