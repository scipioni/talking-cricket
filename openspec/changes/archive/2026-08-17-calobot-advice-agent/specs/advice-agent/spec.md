## Purpose

Answers open-ended questions about the user's own logged food, weight and activity by
retrieving the relevant slice of their diary and explaining it, so that the bot can
respond to questions nobody hardcoded an aggregation for without ever inventing a
number or touching stored data.

## ADDED Requirements

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

Every quantity the system states in an answer — a total, an average, a difference, a
count, a budget or a projection — SHALL be produced by the same deterministic
computation that produces the bot's reports. The language model SHALL select which
data to retrieve and SHALL phrase the explanation, and SHALL NOT compute, derive,
adjust or round any figure that is presented to the user.

#### Scenario: Total asked for directly

- **WHEN** a user asks how many calories they ate in a period
- **THEN** the figure stated is the one the reporting computation returns for that
  period, identical to what a report for the same period would show

#### Scenario: Model states a figure it was not given

- **WHEN** the model's answer contains a quantity that no retrieval returned
- **THEN** the system does not present that quantity to the user as a fact about
  their data

### Requirement: The agent's data access is read-only

The tools available to the agent SHALL be read-only. An advice interaction SHALL NOT
create, modify, soft-delete or hard-delete any food, weight or activity entry, and
SHALL NOT alter the user's profile, goal or budget. No advice interaction SHALL
produce a claim that anything was recorded, changed or removed.

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
value.

#### Scenario: Product does not track the requested quantity

- **WHEN** a user asks about macronutrients, sodium, sugar or any other quantity the
  bot does not record
- **THEN** the system says plainly that it does not track it, and does not produce an
  estimate

#### Scenario: Nothing logged in the period asked about

- **WHEN** a user asks about a period in which they logged nothing
- **THEN** the system says there is no data for that period rather than answering
  from an adjacent period or from general knowledge

#### Scenario: Too little data to support the answer

- **WHEN** a question needs a behavioural pattern but the period holds too few
  logged days to establish one
- **THEN** the system says so rather than asserting a pattern

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

A message on a medical, clinical, pharmacological or eating-disorder topic SHALL be
refused before any model call and before any data retrieval, as it is on the
conversational path. The agent SHALL NOT give medical or clinical advice, and SHALL
remain within the safety limits the user-profile capability defines.

#### Scenario: Medical question reaches the agent

- **WHEN** a user asks the agent about a medical condition, a medication or a
  clinical eating problem
- **THEN** the system declines, says it is not a medical tool, suggests a health
  professional, and performs no retrieval and no model call for it

#### Scenario: Medical framing wrapped around a data question

- **WHEN** a message asks for a clinical judgement about the user's own logged data
- **THEN** the system does not deliver a clinical judgement, whatever the data shows
