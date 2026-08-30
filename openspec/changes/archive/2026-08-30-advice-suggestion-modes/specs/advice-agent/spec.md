## MODIFIED Requirements

### Requirement: Reported figures come from deterministic computation

Every quantity the system states about the user's logged food, weight or activity — a
total, an average, a difference, a count, a budget, a remaining balance or a
projection — SHALL be produced by the same deterministic computation that produces the
bot's reports. The language model SHALL select which data to retrieve and SHALL phrase
the explanation, and SHALL NOT compute, derive, adjust or round any such figure that is
presented to the user. A figure about food the user has not eaten is not a figure about
their logged data and is governed by the requirement on estimated figures for suggested
dishes.

#### Scenario: Total asked for directly

- **WHEN** a user asks how many calories they ate in a period
- **THEN** the figure stated is the one the reporting computation returns for that
  period, identical to what a report for the same period would show

#### Scenario: Model states a figure it was not given

- **WHEN** the model's answer contains a quantity about the user's logged data that no
  retrieval returned
- **THEN** the system does not present that quantity to the user as a fact about
  their data

#### Scenario: Remaining balance stated in a suggestion

- **WHEN** an answer suggesting what to eat states how many calories remain today
- **THEN** that figure is the one the deterministic budget computation returned, not a
  figure the model arrived at itself

### Requirement: Budget-appropriate meal and recipe suggestions

When a user asks for meal or recipe suggestions, the system SHALL determine the
applicable suggestion situation and the day's remaining calorie balance deterministically
before the answer is composed, and SHALL suggest healthy, realistic, Italian-style recipe
ideas that fit within that remaining balance when it is positive. The system SHALL also
retrieve the user's food entries from the last few days and take their variety and
apparent macronutrient balance into account when framing the suggestion, reasoning about
it qualitatively from the food descriptions (e.g. noting an apparent lack of a protein
source, or a run of high-density foods) in the same way the dietician review does, and
SHALL NOT state a specific gram amount of any macronutrient, since the system does not
track macronutrients as structured data. Retrieving the remaining balance and the recent
food entries SHALL NOT depend on the language model choosing to perform two separate
retrievals.

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

### Requirement: Empathetic counseling for budget deficits

When the user asks for meal or recipe suggestions and the deterministically computed
remaining balance for the day is zero or negative, the system SHALL NOT encourage
skipping meals or fasting. Instead, the answer SHALL provide empathetic, supportive
counseling and suggest high-volume, extremely low-density foods (under 100 kcal/100g,
such as clear broths, celery, or fennel) to provide physical satiety and comfort safely.
The suggestion SHALL stay within a fixed low calorie ceiling defined by the system rather
than one chosen by the language model, and an answer whose own declared suggestion
exceeds that ceiling SHALL NOT be delivered as written.

#### Scenario: Recipe suggestion when over budget
- **WHEN** the user asks what to eat but has exceeded their calorie budget by 150 kcal
- **THEN** the agent acknowledges the deficit empathetically, encourages the user not to skip the meal, and suggests a low-density, comforting food option of very low calorie count within the system's ceiling

#### Scenario: Remaining balance is exactly zero
- **WHEN** the user asks what to eat and has consumed exactly their available calories for the day
- **THEN** the answer follows the over-budget counseling behaviour rather than suggesting a meal within a remaining balance of zero

## ADDED Requirements

### Requirement: The suggestion situation is determined outside the language model

Which suggestion situation applies — a positive remaining balance, an exhausted or
exceeded balance, or no computable budget — SHALL be derived by deterministic
computation from the user's stored data, and SHALL NOT be a judgement the language model
makes by comparing figures itself. The model MAY judge, from the user's words, that a
message is asking for a meal suggestion at all; everything that follows from the day's
figures SHALL be decided deterministically.

#### Scenario: Situation follows the data, not the wording

- **WHEN** a user asks what to eat and their remaining balance is negative, whatever
  words they used to ask
- **THEN** the over-budget counseling behaviour applies, because the situation was
  derived from the computed balance

#### Scenario: User misstates their own situation

- **WHEN** a user asks what to eat and claims in the message to be over budget while the
  computed remaining balance is positive
- **THEN** the situation derived from the computed balance governs the answer, and the
  claim in the message does not select a different behaviour

### Requirement: Estimated figures for suggested dishes

A calorie figure the system states for a dish it is suggesting, which the user has not
eaten, is an estimate rather than a computed fact. Such a figure SHALL be presented as
approximate, SHALL NOT be stored, and SHALL NOT be added to, subtracted from, or
otherwise combined with a logged total or a computed budget in a way that presents it as
an equivalent quantity.

#### Scenario: Suggested dish carries an estimated figure

- **WHEN** the system proposes a dish and states roughly how many calories it would be
- **THEN** the figure is framed as an approximation rather than as a value from the
  user's diary

#### Scenario: Suggestion is not treated as a log entry

- **WHEN** the system suggests a dish with an estimated calorie figure
- **THEN** nothing is recorded, the day's totals and remaining balance are unchanged,
  and no later report or answer reflects the suggested dish

### Requirement: An answer inconsistent with the determined situation is not delivered

Before a suggestion answer reaches the user, the system SHALL verify that it corresponds
to the situation that was deterministically derived. An answer that narrates a different
situation than the one derived, or that declares a suggestion exceeding the ceiling the
derived situation imposes, SHALL NOT be delivered as written. The user SHALL instead
receive a safe reply appropriate to the derived situation, and SHALL NOT receive an
internal error, a diagnostic, or a message implying they did something wrong.

#### Scenario: Answer narrates the wrong situation

- **WHEN** the derived situation is an exceeded budget but the composed answer speaks as
  though calories remained
- **THEN** that answer is not delivered, and the user receives a safe reply for the
  exceeded-budget situation instead

#### Scenario: Suggestion exceeds the ceiling for its situation

- **WHEN** the derived situation imposes a low calorie ceiling and the composed answer
  declares a suggestion above it
- **THEN** that answer is not delivered as written

#### Scenario: Substituted reply reads as an answer

- **WHEN** an answer is suppressed for inconsistency with the derived situation
- **THEN** the reply the user receives is a plain, useful response to their question,
  with no internal error text and no suggestion that the user is at fault
