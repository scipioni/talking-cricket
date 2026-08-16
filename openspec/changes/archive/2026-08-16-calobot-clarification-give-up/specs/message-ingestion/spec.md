## MODIFIED Requirements

### Requirement: Draft completeness and the clarification loop

The system SHALL treat an extracted draft as processable only when every field required to compute and store the entry is present. When a draft is not processable, the system SHALL ask the user for exactly the missing information, offer the most common answers as tappable options, accept free text as an alternative, and merge the reply into the open draft.

The system SHALL ask for the same missing field at most a bounded number of consecutive times. When a reply cannot be used to fill the field, the system SHALL count that attempt, and SHALL reset the count as soon as the draft advances. On reaching the limit the system SHALL stop asking, discard the draft, store nothing, and tell the user plainly that the entry was not recorded and that they can send it again. The system SHALL NOT infer or invent the missing value in order to complete a draft the user did not complete.

Each ask after the first SHALL differ from the previous one rather than repeating it verbatim, and SHALL present the tappable options again. While a clarification is open the system SHALL offer the user an explicit way to abandon it, in addition to abandoning implicitly by sending a new loggable message.

The attempt limit SHALL be configurable without code changes.

#### Scenario: Missing quantity

- **WHEN** a user writes "un piatto di pasta al pesto" and the quantity cannot be resolved to grams
- **THEN** the system asks how large the portion was, offering typical portions as tappable options, and does not store an entry yet

#### Scenario: Reply completes the draft

- **WHEN** the user answers a clarification question with the missing value
- **THEN** the system merges it into the open draft and, if the draft is now processable, resolves and stores the entry

#### Scenario: Reply still insufficient

- **WHEN** the user's answer to a clarification question still leaves a required field unresolved, and the attempt limit has not been reached
- **THEN** the system asks again for the field that remains missing, wording the question differently from the previous ask and offering the options again

#### Scenario: User cannot answer at all

- **WHEN** the user gives unusable replies to the same field up to the configured limit
- **THEN** the system stops asking, discards the draft, stores nothing, and tells the user the entry was not recorded and that they can send it again

#### Scenario: Attempts reset when the draft advances

- **WHEN** a user gives some unusable replies and then answers successfully, and a later field also proves hard to fill
- **THEN** the count starts again for the new field rather than carrying over

#### Scenario: A guess is never substituted for an answer

- **WHEN** the attempt limit is reached for a quantity
- **THEN** no entry is stored, and no value is inferred to complete the draft

#### Scenario: User abandons a clarification deliberately

- **WHEN** a clarification is open and the user chooses the offered way out
- **THEN** the system discards the draft, stores nothing, and confirms that nothing was recorded

#### Scenario: User cancels a draft

- **WHEN** a user cancels while a draft is open
- **THEN** the system discards the draft, stores nothing, and confirms the cancellation

#### Scenario: New log message while a draft is open

- **WHEN** a user sends a new, unrelated log message while a clarification is pending
- **THEN** the system discards the pending draft, tells the user it was not recorded, and processes the new message
