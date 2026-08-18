## MODIFIED Requirements

### Requirement: Classification of inbound messages

The system SHALL classify every inbound user message that is not a command into exactly one intent: food, weight, activity, profile, correction, report or other. Classification SHALL precede extraction, and extraction SHALL use a schema specific to the classified intent. A message classified as other SHALL NOT result in any claim that data was recorded. Classification SHALL remain a single schema-validated call and SHALL NOT retrieve stored data in order to decide an intent.

#### Scenario: Food message

- **WHEN** a user writes "ho mangiato 10g di noci"
- **THEN** the message is classified as food and extracted with the food schema

#### Scenario: Weight message

- **WHEN** a user writes "oggi peso 78kg"
- **THEN** the message is classified as weight and extracted with the weight schema

#### Scenario: Activity message

- **WHEN** a user writes "ho fatto una camminata di mezz'ora"
- **THEN** the message is classified as activity and extracted with the activity schema

#### Scenario: Profile message

- **WHEN** a user writes a statement that sets a profile field, such as "ora il mio peso obiettivo è 74kg"
- **THEN** the message is classified as profile and extracted with the profile schema, and the change is handled by the user-profile capability

#### Scenario: A body weight statement is not a profile edit

- **WHEN** a user writes a statement of their current body weight, such as "oggi peso 78kg"
- **THEN** the message is classified as weight rather than profile, because a body weight is a measurement that is logged and not a profile field that is set

#### Scenario: Conversational message

- **WHEN** a user writes something that is neither a log nor a profile change nor a correction nor a report request, such as a greeting or a general nutrition question
- **THEN** the message is classified as other and handed to the advice-agent capability, which answers it within the safety limits of the user-profile capability, without creating any entry and without claiming that any entry was created

#### Scenario: Question about the user's own data

- **WHEN** a user writes a question about their own logged food, weight or activity that is not a request for a standard report, such as "posso permettermi una pizza stasera?"
- **THEN** the message is classified as other and answered by the advice-agent capability using the user's stored data, and no entry is created

#### Scenario: Message mixing two intents

- **WHEN** a user writes a message containing more than one intent, such as "ho mangiato una mela e peso 77kg"
- **THEN** the system processes the dominant intent and tells the user which part it did not record, so nothing is silently dropped

#### Scenario: Message mixing a loggable intent with conversation

- **WHEN** a user writes a message that states a meal alongside conversational text
- **THEN** the message is not treated as conversation, and the meal is extracted and stored

### Requirement: Only the storing path may confirm a record

The system SHALL NOT state or imply that an entry has been created, amended or deleted, or that a profile field has been changed, unless that entry was created, amended or deleted, or that field changed, while handling the message being replied to. A reply produced for the conversational intent SHALL NOT assert that anything was recorded or changed, and this SHALL be enforced after the reply is produced rather than only requested of the language model.

#### Scenario: Conversational reply claims a record was made

- **WHEN** a message is handled as conversation and the generated reply asserts that something was logged
- **THEN** the system does not send that assertion to the user, and no entry is implied to exist

#### Scenario: Conversational reply claims a profile field was changed

- **WHEN** a message is handled as conversation and the generated reply asserts that a profile field was updated, set or changed
- **THEN** the system does not send that assertion to the user, and no profile change is implied to have happened

#### Scenario: Conversational reply makes no such claim

- **WHEN** a message is handled as conversation and the generated reply makes no claim about records
- **THEN** the reply is sent unchanged

#### Scenario: A stored entry is confirmed normally

- **WHEN** an entry is created while handling a message
- **THEN** the confirmation states what was stored, as it does today, and carries the controls that address that entry

#### Scenario: An applied profile change is confirmed normally

- **WHEN** a profile field is changed while handling a message
- **THEN** the confirmation states what changed, as the storing path does for an entry
