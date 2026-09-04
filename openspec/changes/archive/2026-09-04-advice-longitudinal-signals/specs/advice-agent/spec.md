## MODIFIED Requirements

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
