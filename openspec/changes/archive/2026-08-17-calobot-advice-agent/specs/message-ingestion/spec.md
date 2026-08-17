## MODIFIED Requirements

### Requirement: Classification of inbound messages

The system SHALL classify every inbound user message that is not a command into exactly one intent: food, weight, activity, correction, report or other. Classification SHALL precede extraction, and extraction SHALL use a schema specific to the classified intent. A message classified as other SHALL NOT result in any claim that data was recorded. Classification SHALL remain a single schema-validated call and SHALL NOT retrieve stored data in order to decide an intent.

#### Scenario: Food message

- **WHEN** a user writes "ho mangiato 10g di noci"
- **THEN** the message is classified as food and extracted with the food schema

#### Scenario: Weight message

- **WHEN** a user writes "oggi peso 78kg"
- **THEN** the message is classified as weight and extracted with the weight schema

#### Scenario: Activity message

- **WHEN** a user writes "ho fatto una camminata di mezz'ora"
- **THEN** the message is classified as activity and extracted with the activity schema

#### Scenario: Conversational message

- **WHEN** a user writes something that is neither a log nor a correction nor a report request, such as a greeting or a general nutrition question
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

### Requirement: Language model invocation contract

The system SHALL validate every language model response against the schema expected for the current step. On a response that fails to parse or validate, the system SHALL retry a bounded number of times, supplying the validation error. When retries are exhausted, the system SHALL reply with a plain message asking the user to rephrase, and SHALL NOT expose an internal error, stack trace or raw model output to the user.

Where a step invokes the model as an agent that may request retrieval before answering, the same contract SHALL hold at the boundaries: arguments the model supplies for a retrieval SHALL be validated before the retrieval runs, the final answer SHALL be schema-validated as any other response is, and the number of retrieval rounds SHALL be bounded. Exhausting that bound SHALL be reported to the user as a plain message, as an exhausted retry limit is.

#### Scenario: Malformed response recovered by retry

- **WHEN** the model returns output that does not satisfy the expected schema and a retry returns valid output
- **THEN** the system proceeds normally and the user sees no error

#### Scenario: Retries exhausted

- **WHEN** the model fails to return schema-valid output within the retry limit
- **THEN** the system asks the user to rephrase and stores nothing

#### Scenario: Endpoint unreachable or timed out

- **WHEN** the language model endpoint is unreachable or does not respond within the configured timeout
- **THEN** the system tells the user the service is temporarily unavailable and invites them to retry, and stores nothing

#### Scenario: Invalid retrieval arguments from the model

- **WHEN** the model requests a retrieval with arguments that do not validate against that retrieval's schema
- **THEN** the retrieval does not run, the model is told the arguments were rejected, and no internal error reaches the user

#### Scenario: Retrieval bound exhausted

- **WHEN** an agentic step reaches its bound on retrieval rounds without producing an answer
- **THEN** the user receives a plain message inviting them to ask more specifically, and no partial result is presented as an answer
