## ADDED Requirements

### Requirement: Budget-appropriate meal and recipe suggestions

When a user asks for meal or recipe suggestions, the agent SHALL retrieve the user's profile and calorie budget, determine the remaining calorie balance for the day, and suggest healthy, realistic, Italian-style recipe ideas that fit within that remaining budget.

#### Scenario: Recipe suggestion within budget
- **WHEN** the user asks "cosa posso mangiare stasera" and has a positive remaining calorie balance today (such as 400 kcal)
- **THEN** the agent suggests healthy recipes whose estimated calories do not exceed the remaining balance, explicitly referencing the remaining calorie figure in the response

### Requirement: Empathetic counseling for budget deficits

When the user asks for meal or recipe suggestions but has already exceeded their daily calorie budget (resulting in a negative remaining balance), the agent SHALL NOT encourage skipping meals or fasting. Instead, the agent SHALL provide empathetic, supportive counseling and suggest high-volume, extremely low-density foods (under 100 kcal/100g, such as clear broths, celery, or fennel) to provide physical satiety and comfort safely.

#### Scenario: Recipe suggestion when over budget
- **WHEN** the user asks what to eat but has exceeded their calorie budget by 150 kcal
- **THEN** the agent acknowledges the deficit empathetically, encourages the user not to skip the meal, and suggests a low-density, comforting food option of very low calorie count (such as under 100 kcal total)

## MODIFIED Requirements

### Requirement: Existing safety limits apply to the agent

A message on a medical, clinical, pharmacological, eating-disorder, metabolic, or cardiovascular topic (specifically including high/low cholesterol, blood pressure, and hypertension) SHALL be refused before any model call and before any data retrieval, as it is on the conversational path. The agent SHALL NOT give medical or clinical advice, and SHALL remain within the safety limits the user-profile capability defines.

#### Scenario: Medical question reaches the agent

- **WHEN** a user asks the agent about a medical condition, a medication or a
  clinical eating problem
- **THEN** the system declines, says it is not a medical tool, suggests a health
  professional, and performs no retrieval and no model call for it

#### Scenario: Medical framing wrapped around a data question

- **WHEN** a message asks for a clinical judgement about the user's own logged data
- **THEN** the system does not deliver a clinical judgement, whatever the data shows

#### Scenario: Chronic metabolic or cardiovascular condition asked about

- **WHEN** a user asks for advice or meal suggestions regarding high cholesterol, blood pressure, or hypertension
- **THEN** the system declines using the standard medical refusal, performing no retrieval and no model call
