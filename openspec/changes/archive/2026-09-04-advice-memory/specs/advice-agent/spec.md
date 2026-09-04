## MODIFIED Requirements

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
