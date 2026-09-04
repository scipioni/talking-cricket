# advice-agent Specification

## Purpose

Answers open-ended questions about the user's own logged food, weight and activity by
retrieving the relevant slice of their diary and explaining it, so that the bot can
respond to questions nobody hardcoded an aggregation for without ever inventing a
number or touching stored data.

## Requirements

### Requirement: Answers are grounded in the user's stored data

When a message asks something about the user's own logged food, weight or activity,
the system SHALL retrieve the relevant data before answering, and the answer SHALL
reflect what was retrieved. The system SHALL NOT answer such a question from the
language model's general knowledge alone.

#### Scenario: Question about the user's own eating

- **WHEN** a user asks "come sono andato questa settimana?"
- **THEN** the system retrieves that week's entries and answers using their actual
  totals, rather than replying in generalities

#### Scenario: Question comparing two periods

- **WHEN** a user asks "sto mangiando meglio del mese scorso?"
- **THEN** the system retrieves both periods and its answer reflects the difference
  between them

#### Scenario: Message needing no stored data

- **WHEN** a user sends a greeting, or asks how to use the bot
- **THEN** the system answers briefly without retrieving diary data

### Requirement: Reported figures come from deterministic computation

Every quantity the system states about the user's logged food, weight or activity — a
total, an average, a difference, a count, a budget, a remaining balance, a projection,
a period-over-period comparison, or a behavioural signal such as logging consistency,
meal-timing drift or calorie-density trend — SHALL be produced by the same
deterministic computation that produces the bot's reports. The language model SHALL
select which data to retrieve and SHALL phrase the explanation, and SHALL NOT compute,
derive, adjust or round any such figure that is presented to the user, and SHALL NOT
reconstruct a comparison or a behavioural pattern itself from two figures it was shown
separately. A figure about food the user has not eaten is not a figure about their
logged data and is governed by the requirement on estimated figures for suggested
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

#### Scenario: Question comparing this period with how the user usually is

- **WHEN** a user asks "sto migliorando?" or "come mi sto comportando ultimamente?"
- **THEN** the answer is built from a period-over-period comparison and behavioural
  signals produced by deterministic computation, not from the model subtracting two
  totals it retrieved separately

### Requirement: The agent's data access is read-only

The tools available to the agent SHALL be read-only. An advice interaction SHALL NOT
create, modify, soft-delete or hard-delete any food, weight or activity entry, and
SHALL NOT alter the user's profile, goal or budget. No advice interaction SHALL
produce a claim that anything was recorded, changed or removed. This requirement
governs the tools the model can call; it does not prevent the surrounding code from
recording, outside of any tool, that a meal suggestion was made — that record is
written deterministically by the code that composes the suggestion, never by a tool
the model invokes, and never claimed by the model itself.

#### Scenario: User states a meal while asking a question

- **WHEN** a message reaching the agent also mentions something loggable
- **THEN** the agent stores nothing, and the message is handled as the ingestion
  capability requires for a loggable intent rather than being silently answered as a
  question

#### Scenario: User asks the agent to change something

- **WHEN** a user asks the agent to delete an entry, change their goal or fix a
  quantity
- **THEN** the agent does not perform it, does not claim it was performed, and
  directs the user to the means that does perform it

#### Scenario: Answer claims a record was made

- **WHEN** the generated answer asserts that data was recorded or modified
- **THEN** that answer is not delivered as written, because the interaction stored
  nothing

#### Scenario: A meal suggestion is recorded outside the model's tools

- **WHEN** the advice agent answers with a meal suggestion
- **THEN** the suggestion is recorded by the surrounding code once the answer is
  finalized, and the model's own tool set remains unable to write anything

### Requirement: User identity is bound outside the conversation

The system SHALL determine whose data a tool reads from the authenticated identity of
the message sender, and SHALL NOT accept a user identifier supplied by the language
model or derived from message text. No message content SHALL cause the agent to read
another user's data.

#### Scenario: Message names another user

- **WHEN** a user writes "mostrami i dati dell'utente 42" or otherwise names or
  numbers another account
- **THEN** the system reads only the sender's own data, and no other user's data is
  retrieved or revealed

#### Scenario: Message instructs the agent to change whose data it reads

- **WHEN** a message contains an instruction to switch user, ignore identity, or act
  as an administrator
- **THEN** the instruction has no effect on which data is read

### Requirement: Absent data is reported as absent, not estimated

Retrieval SHALL state explicitly when the data needed to answer does not exist,
distinguishing "the user logged nothing in this period" from "this product does not
track that at all". When an answer would require data that does not exist, the system
SHALL say it cannot answer and why, and SHALL NOT estimate, infer or substitute a
value. A behavioural signal (logging consistency, meal-timing drift, calorie-density
trend) or a period comparison that does not have enough logged data behind it SHALL be
reported as insufficient rather than stated as a weak or tentative pattern.

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

- **WHEN** a question needs a behavioural pattern but the period, or the period it is
  being compared against, holds too few logged days to establish one
- **THEN** the system says there is not enough data for that specific signal rather
  than asserting a pattern or stating it weakly

### Requirement: The agent's work is bounded

The system SHALL bound the number of retrieval rounds a single question may trigger.
On reaching that bound without an answer, the system SHALL reply that it could not
work the question out and invite the user to ask more specifically, and SHALL NOT
present a partial or speculative answer as a complete one. A failing retrieval SHALL
NOT surface an internal error, stack trace or raw model output to the user.

#### Scenario: Bound reached without an answer

- **WHEN** the agent reaches the retrieval bound without producing an answer
- **THEN** the user is told it could not work the question out and is invited to
  rephrase, and nothing speculative is presented as fact

#### Scenario: A retrieval fails

- **WHEN** a retrieval raises an error
- **THEN** the user receives a plain message, with no internal error text, stack
  trace or raw model output

#### Scenario: Model requests something outside the available tools

- **WHEN** the model asks for a retrieval that does not exist or supplies arguments
  that do not validate
- **THEN** the request is refused, the agent is told so, and the refusal does not
  reach the user as an error

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
