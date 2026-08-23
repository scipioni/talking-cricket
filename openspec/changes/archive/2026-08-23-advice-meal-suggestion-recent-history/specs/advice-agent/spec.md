## MODIFIED Requirements

### Requirement: Budget-appropriate meal and recipe suggestions

When a user asks for meal or recipe suggestions, the agent SHALL retrieve the user's profile and calorie budget, determine the remaining calorie balance for the day, and suggest healthy, realistic, Italian-style recipe ideas that fit within that remaining budget. The agent SHALL also retrieve the user's food entries from the last few days and take their variety and apparent macronutrient balance into account when framing the suggestion, reasoning about it qualitatively from the food descriptions (e.g. noting an apparent lack of a protein source, or a run of high-density foods) in the same way the dietician review does, and SHALL NOT state a specific gram amount of any macronutrient, since the system does not track macronutrients as structured data.

#### Scenario: Recipe suggestion within budget
- **WHEN** the user asks "cosa posso mangiare stasera" and has a positive remaining calorie balance today (such as 400 kcal)
- **THEN** the agent suggests healthy recipes whose estimated calories do not exceed the remaining balance, explicitly referencing the remaining calorie figure in the response

#### Scenario: Recipe suggestion informed by recent variety
- **WHEN** the user asks for a meal suggestion and their food entries from the last few days show no apparent protein source
- **THEN** the agent's suggestion leans toward a protein-containing option and may say so, without stating a specific gram amount of protein

#### Scenario: No recent food data to reason from
- **WHEN** the user asks for a meal suggestion and no food entries exist in the last few days
- **THEN** the agent still suggests a recipe within the remaining calorie budget, without asserting anything about recent variety

### Requirement: Empathetic counseling for budget deficits

When the user asks for meal or recipe suggestions but has already exceeded their daily calorie budget (resulting in a negative remaining balance), the agent SHALL NOT encourage skipping meals or fasting. Instead, the agent SHALL provide empathetic, supportive counseling and suggest high-volume, extremely low-density foods (under 100 kcal/100g, such as clear broths, celery, or fennel) to provide physical satiety and comfort safely.

#### Scenario: Recipe suggestion when over budget
- **WHEN** the user asks what to eat but has exceeded their calorie budget by 150 kcal
- **THEN** the agent acknowledges the deficit empathetically, encourages the user not to skip the meal, and suggests a low-density, comforting food option of very low calorie count (such as under 100 kcal total)
