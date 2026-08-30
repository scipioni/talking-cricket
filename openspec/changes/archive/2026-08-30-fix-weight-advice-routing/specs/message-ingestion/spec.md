## MODIFIED Requirements

### Requirement: Classification of inbound messages

The system SHALL classify every inbound user message that is not a command into exactly one intent: food, weight, activity, profile, correction, report or other. Classification SHALL precede extraction, and extraction SHALL use a schema specific to the classified intent. A message classified as other SHALL NOT result in any claim that data was recorded. Classification SHALL remain a single schema-validated call and SHALL NOT retrieve stored data in order to decide an intent. 

When a user specifies a vague loggable item (such as a generic food name without quantities), the system SHALL classify the message as that loggable intent (e.g., food) rather than conversational (other), allowing it to enter the standard clarification loop to resolve the missing fields.

#### Scenario: Food message

- **WHEN** a user writes "ho mangiato 10g di noci"
- **THEN** the message is classified as food and extracted with the food schema

#### Scenario: Vague food message

- **WHEN** a user writes a vague food entry like "boh, pasta?"
- **THEN** the message is classified as food and the missing quantity triggers the clarification loop, rather than being classified as conversational (other)

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

#### Scenario: Analytical weight-loss advice question

- **WHEN** a user writes an analytical weight-loss or progress-tracking question asking for calculations or estimates (e.g., "quanti kg avrei dovuto perdere?", "perché non perdo peso?")
- **THEN** the message is classified as other and answered by the advice-agent capability using the user's stored data, rather than being classified as report (which would search for logged weight measurements and report no data is present)

#### Scenario: Message mixing two loggable intents

- **WHEN** a user writes a message containing more than one actionable, loggable intent, such as "ho mangiato una mela e peso 77kg"
- **THEN** the system processes the dominant intent and tells the user which actionable part it did not record, so nothing is silently dropped

#### Scenario: Message mixing a loggable intent with conversation

- **WHEN** a user writes a message that states a meal alongside conversational text or fluff (e.g. "ho mangiato una mela, ecco i log")
- **THEN** the message is not treated as conversation, the meal is extracted and stored, and the conversational fluff is ignored silently without triggering a warning about unrecorded text

#### Scenario: Message with a self-contradiction

- **WHEN** a user writes a single message correcting themselves (e.g. "volevo registrare la pizza ma ho mangiato un'insalata")
- **THEN** the system resolves the contradiction, classifies and extracts the final intent (the salad), and ignores the discarded intent silently rather than treating it as unhandled text or an edit of a past entry
