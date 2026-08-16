# user-profile Specification

## Purpose

Holds each Telegram user's identity and anthropometric profile, and derives from it the daily calorie budget that every report is measured against. Without a complete profile the system cannot produce a target, so this capability also owns the onboarding conversation and the safety limits applied to goals.

## Requirements

### Requirement: Autoregistration on /start

The system SHALL create a user record on the first `/start` command from a Telegram account, keyed by the Telegram user id, without requiring any credentials.

#### Scenario: First contact

- **WHEN** a Telegram account sends `/start` and no user record exists for its id
- **THEN** the system creates a user record, stores the Telegram id, and begins onboarding

#### Scenario: Returning user with a complete profile

- **WHEN** a Telegram account sends `/start` and a user record with a complete profile already exists
- **THEN** the system does not create a duplicate record, does not reset the profile, and replies with a short summary of the current profile and daily budget

#### Scenario: Returning user with an incomplete profile

- **WHEN** a Telegram account sends `/start` and a user record exists whose onboarding never completed
- **THEN** the system resumes onboarding from the first missing field rather than starting over

### Requirement: Profile fields

The system SHALL maintain, for each user, the following fields: sesso, data di nascita, altezza in centimetri, peso attuale in chilogrammi, peso obiettivo in chilogrammi, livello di attività and ritmo di variazione del peso desiderato. Age SHALL be derived from data di nascita at the time of each calculation and never stored as a static number.

#### Scenario: Age is recomputed, not stored

- **WHEN** a user's daily budget is computed on any date
- **THEN** the age used is the age at that date, derived from data di nascita

#### Scenario: Rejecting an implausible value

- **WHEN** a user supplies a value outside the plausible range for its field (for example an altezza below 100 cm or above 250 cm, or a peso below 30 kg or above 400 kg)
- **THEN** the system rejects the value, explains the accepted range, and asks again without storing it

#### Scenario: Activity level is editable

- **WHEN** a user changes their livello di attività after onboarding
- **THEN** the system stores the new value with the date it took effect, retains the previous value, and recomputes the daily budget

### Requirement: Welcome message on first contact

Before asking the first onboarding question, the system SHALL send a welcome message, in Italian, that: briefly explains the bot's purpose and capabilities (logging food, weight and activity through free-form chat, and receiving reports); names the data sources it relies on (an LLM for interpreting messages, and the bundled food composition and activity tables); and states plainly that it is experimental software, not a medical aid, provided without liability on the author's part. This message SHALL be shown once, on first contact, and SHALL NOT be repeated on every resumed onboarding message.

#### Scenario: First contact welcome

- **WHEN** a Telegram account sends `/start` for the first time
- **THEN** the system sends the welcome message before asking the first onboarding question

#### Scenario: Welcome not repeated on resume

- **WHEN** a returning user with incomplete onboarding sends another message
- **THEN** the system does not resend the welcome message, only the next missing question

### Requirement: Onboarding conversation

The system SHALL collect the profile through conversation rather than a form. Enumerated fields (sesso, livello di attività, ritmo) SHALL be offered as tappable options, while free text answers SHALL always be accepted for any field. Onboarding SHALL be resumable: a partially completed profile SHALL survive a restart of the service and be continued at the user's next message.

#### Scenario: Multiple fields in one message

- **WHEN** a user answers with several values at once, such as "41 anni, 1.78, 78kg, vorrei arrivare a 72"
- **THEN** the system records every field it could extract and asks only for the fields still missing

#### Scenario: Enumerated field offered as options

- **WHEN** the system asks for livello di attività
- **THEN** it presents the available levels as tappable options and also accepts a free text answer

#### Scenario: Onboarding interrupted and resumed

- **WHEN** a user abandons onboarding partway and returns after the service has been restarted
- **THEN** the previously supplied fields are still present and the system asks only for what remains

#### Scenario: Disclaimer presented

- **WHEN** onboarding completes
- **THEN** the system states that Calobot is a tracking tool and not medical advice, before reporting the daily budget

### Requirement: Daily calorie budget derivation

The system SHALL derive a daily calorie budget as basal metabolic rate computed with the Mifflin-St Jeor equation, multiplied by the factor for the user's livello di attività, minus the daily deficit implied by the ritmo desiderato. The budget SHALL be recomputed whenever any input field changes, including when a new weight is logged.

#### Scenario: Budget available after onboarding

- **WHEN** the last required profile field is supplied
- **THEN** the system computes the daily budget and reports it to the user

#### Scenario: Budget follows current weight

- **WHEN** a user logs a new weight
- **THEN** the daily budget is recomputed using that weight

#### Scenario: Goal implies gaining weight

- **WHEN** a user's peso obiettivo is above their peso attuale
- **THEN** the system applies the ritmo as a surplus rather than a deficit

#### Scenario: Goal already reached

- **WHEN** a user's peso attuale has reached their peso obiettivo
- **THEN** the system applies no deficit or surplus, reports a maintenance budget, and tells the user the goal is reached

### Requirement: Safety limits on goals and budgets

The system SHALL NOT produce a daily budget below 1500 kcal for men or 1200 kcal for women; if the requested ritmo would go below that floor, the system SHALL clamp the budget to the floor and tell the user it has done so. The system SHALL warn a user whose peso obiettivo implies a body mass index below 18.5 and SHALL refuse to set that goal. The system SHALL NOT give medical, clinical or eating-disorder advice, and SHALL direct the user to a health professional when a message indicates such a need.

#### Scenario: Deficit would breach the floor

- **WHEN** a user selects a ritmo whose deficit would put the budget below the applicable floor
- **THEN** the system sets the budget to the floor, explains that the requested pace has been reduced for safety, and states the resulting realistic pace

#### Scenario: Unsafe goal weight

- **WHEN** a user sets a peso obiettivo implying a body mass index below 18.5
- **THEN** the system refuses the goal, explains why, and asks for a different value

#### Scenario: Request for medical advice

- **WHEN** a user asks about a medical condition, medication, or a clinical eating problem
- **THEN** the system declines to advise, says plainly that it is not a medical tool, and suggests consulting a health professional

### Requirement: Profile inspection, editing and deletion

The system SHALL let a user view their current profile and derived budget, change any single field, and delete all their data permanently.

#### Scenario: Viewing the profile

- **WHEN** a user asks to see their profile
- **THEN** the system reports every stored field and the current daily budget

#### Scenario: Deleting all data

- **WHEN** a user requests deletion of their data and confirms the request
- **THEN** the system permanently removes the user's profile and all their logged entries, and confirms the deletion
