## Why

While Calobot excels at the mechanical accounting of calorie logging, traditional logs are passive ledgers that do not offer behavioral or actionable guidance. This change elevates Calobot from a simple ledger to a companion AI dietician by providing warm, clinical, and encouraging weekly or monthly nutritional critiques in Italian. These reviews help users understand eating timing, volumetric calorie density, and logging accuracy patterns without needing to track tedious macronutrients.

## What Changes

- **Dietician Review Section**: Add a structured, encouraging behavioral dietician's critique to the end of food and combined ("all") reports covering periods of a week or longer.
- **Nutritional Persona Prompting**: Introduce a dedicated professional clinician system prompt that interprets calorie density, consumption timestamps, logging consistency, and data provenance.
- **Structured Pydantic Outputs**: Guarantee that the LLM response always conforms to a specific structured schema (`DieticianReview`) so that reports are reliable, safe, and easily rendered into consistent Italian Markdown.

## Capabilities

### New Capabilities

- `dietician-reviews`: Under `specs/dietician-reviews/spec.md`, defining the structured extraction of behavioral insights (calorie density, temporal timing, sourcing quality) using a clinical Italian persona, and returning a predictable JSON schema.

### Modified Capabilities

- `reporting`: Under `openspec/specs/reporting/spec.md`, modifying the food report requirements to append the generated dietician review when the report covers a week or a month.

## Impact

- **Database / API**: None. We read existing `FoodEntry` records and do not require database migrations or schema alterations since macronutrients are not tracked.
- **LLM Gateway**: Extends the `LLMGateway` calls with a new step and prompt.
- **Reporting Module**: Updates `src/calobot/reporting/aggregation.py` or the ingestion pipeline to build the dietician review using the raw food entries from the queried period.
- **User Interface**: Enhances the Telegram reporting text blocks with a clean, formatted dietician section under the calorie chart.
