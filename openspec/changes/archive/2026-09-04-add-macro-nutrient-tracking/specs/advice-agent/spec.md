## MODIFIED Requirements

### Requirement: Absent data is reported as absent, not estimated

Retrieval SHALL state explicitly when the data needed to answer does not exist,
distinguishing "the user logged nothing in this period" from "this product does not
track that at all". When an answer would require data that does not exist, the system
SHALL say it cannot answer and why, and SHALL NOT estimate, infer or substitute a
value.

#### Scenario: Product does not track the requested quantity

- **WHEN** a user asks about sodium, sugar or any other quantity the bot does not
  record
- **THEN** the system says plainly that it does not track it, and does not produce an
  estimate

#### Scenario: User asks about macronutrients conversationally

- **WHEN** a user asks the agent about macronutrients (e.g. how much protein they ate)
  outside of a standard report request
- **THEN** the agent does not estimate or invent a figure, and tells the user to ask for
  a macro report instead, since macronutrients are tracked but this conversational path
  has no retrieval for them

#### Scenario: Nothing logged in the period asked about

- **WHEN** a user asks about a period in which they logged nothing
- **THEN** the system says there is no data for that period rather than answering
  from an adjacent period or from general knowledge

#### Scenario: Too little data to support the answer

- **WHEN** a question needs a behavioural pattern but the period holds too few
  logged days to establish one
- **THEN** the system says so rather than asserting a pattern

### Requirement: Budget-appropriate meal and recipe suggestions

When a user asks for meal or recipe suggestions, the system SHALL determine the
applicable suggestion situation and the day's remaining calorie balance deterministically
before the answer is composed, and SHALL suggest healthy, realistic, Italian-style recipe
ideas that fit within that remaining balance when it is positive. The system SHALL also
retrieve the user's food entries from the last few days and take their variety and
apparent macronutrient balance into account when framing the suggestion, reasoning about
it qualitatively from the food descriptions (e.g. noting an apparent lack of a protein
source, or a run of high-density foods) in the same way the dietician review does, and
SHALL NOT state a specific gram amount of any macronutrient in this suggestion — a
deliberate choice to keep a conversational suggestion qualitative and non-clinical in
tone, independent of whether macro grams are recorded elsewhere in the reporting
capability. Retrieving the remaining balance and the recent food entries SHALL NOT depend
on the language model choosing to perform two separate retrievals.

#### Scenario: Recipe suggestion within budget
- **WHEN** the user asks "cosa posso mangiare stasera" and has a positive remaining calorie balance today (such as 400 kcal)
- **THEN** the agent suggests healthy recipes whose estimated calories do not exceed the remaining balance, explicitly referencing the remaining calorie figure in the response

#### Scenario: Recipe suggestion informed by recent variety
- **WHEN** the user asks for a meal suggestion and their food entries from the last few days show no apparent protein source
- **THEN** the agent's suggestion leans toward a protein-containing option and may say so, without stating a specific gram amount of protein

#### Scenario: No recent food data to reason from
- **WHEN** the user asks for a meal suggestion and no food entries exist in the last few days
- **THEN** the agent still suggests a recipe within the remaining calorie budget, without asserting anything about recent variety

#### Scenario: Profile incomplete so no budget exists
- **WHEN** the user asks for a meal suggestion and their profile is not complete enough for a calorie budget to be computed
- **THEN** the system does not state or imply a remaining balance, and does not present an invented budget figure
