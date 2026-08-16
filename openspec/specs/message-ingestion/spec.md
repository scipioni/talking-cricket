# message-ingestion Specification

## Purpose

Turns an unstructured Italian chat message into a typed, complete and validated draft that another capability can store. This is the layer that makes the product feel like conversation rather than data entry, and it owns the rules that keep an unreliable language model from producing wrong or unusable records.

## Requirements

### Requirement: Classification of inbound messages

The system SHALL classify every inbound user message that is not a command into exactly one intent: food, weight, activity, correction, report or other. Classification SHALL precede extraction, and extraction SHALL use a schema specific to the classified intent.

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
- **THEN** the message is classified as other and answered conversationally, within the safety limits of the user-profile capability, without creating any entry

#### Scenario: Message mixing two intents

- **WHEN** a user writes a message containing more than one intent, such as "ho mangiato una mela e peso 77kg"
- **THEN** the system processes the dominant intent and tells the user which part it did not record, so nothing is silently dropped

### Requirement: Draft completeness and the clarification loop

The system SHALL treat an extracted draft as processable only when every field required to compute and store the entry is present. When a draft is not processable, the system SHALL ask the user for exactly the missing information, offer the most common answers as tappable options, accept free text as an alternative, and merge the reply into the open draft. The system SHALL continue asking until the draft is processable or the user abandons or cancels it.

#### Scenario: Missing quantity

- **WHEN** a user writes "un piatto di pasta al pesto" and the quantity cannot be resolved to grams
- **THEN** the system asks how large the portion was, offering typical portions as tappable options, and does not store an entry yet

#### Scenario: Reply completes the draft

- **WHEN** the user answers a clarification question with the missing value
- **THEN** the system merges it into the open draft and, if the draft is now processable, resolves and stores the entry

#### Scenario: Reply still insufficient

- **WHEN** the user's answer to a clarification question still leaves a required field unresolved
- **THEN** the system asks again for the field that remains missing

#### Scenario: User cancels a draft

- **WHEN** a user cancels while a draft is open
- **THEN** the system discards the draft, stores nothing, and confirms the cancellation

#### Scenario: New log message while a draft is open

- **WHEN** a user sends a new, unrelated log message while a clarification is pending
- **THEN** the system discards the pending draft, tells the user it was not recorded, and processes the new message

### Requirement: Draft persistence

The system SHALL persist open drafts so that a pending clarification survives a restart of the service. A draft SHALL expire after a bounded period of inactivity and SHALL NOT be stored as a completed entry when it expires.

#### Scenario: Restart during clarification

- **WHEN** the service restarts while a clarification is pending and the user then answers
- **THEN** the answer is merged into the draft that was open before the restart

#### Scenario: Draft expires

- **WHEN** an open draft receives no reply within the inactivity period
- **THEN** the draft is discarded without creating an entry

### Requirement: Language model invocation contract

The system SHALL validate every language model response against the schema expected for the current step. On a response that fails to parse or validate, the system SHALL retry a bounded number of times, supplying the validation error. When retries are exhausted, the system SHALL reply with a plain message asking the user to rephrase, and SHALL NOT expose an internal error, stack trace or raw model output to the user.

#### Scenario: Malformed response recovered by retry

- **WHEN** the model returns output that does not satisfy the expected schema and a retry returns valid output
- **THEN** the system proceeds normally and the user sees no error

#### Scenario: Retries exhausted

- **WHEN** the model fails to return schema-valid output within the retry limit
- **THEN** the system asks the user to rephrase and stores nothing

#### Scenario: Endpoint unreachable or timed out

- **WHEN** the language model endpoint is unreachable or does not respond within the configured timeout
- **THEN** the system tells the user the service is temporarily unavailable and invites them to retry, and stores nothing

### Requirement: Language model configuration

The system SHALL access the language model through an OpenAI-compatible interface whose base URL, model name, temperature, request timeout and retry limit are configurable without code changes, and SHALL allow a different model to be configured per pipeline step.

#### Scenario: Endpoint changed by configuration

- **WHEN** the configured base URL or model name is changed and the service is restarted
- **THEN** the system uses the new endpoint and model with no code modification

### Requirement: Input modality contract

The extraction interface SHALL accept either text or an image as the message content, so that image input can be enabled without restructuring the pipeline. In this version the system SHALL respond to an image by stating that photo recognition is not yet available.

#### Scenario: User sends a photo

- **WHEN** a user sends a photo of a meal
- **THEN** the system replies that photo recognition is not yet supported and stores nothing

### Requirement: Responsiveness feedback

The system SHALL indicate that it is working while a message is being processed, so that a user waiting on model latency is not left without feedback.

#### Scenario: Processing takes noticeable time

- **WHEN** a message requires one or more language model calls
- **THEN** the system shows a typing indicator in the chat until it replies
