# dietician-reviews Specification

## Purpose

Generates personal, clinical, and encouraging behavioral dietician reviews in Italian by analyzing the user's calorie densities, meal timing, and logging habits over a week or a month.

## Requirements

### Requirement: Dietician review generation

The system SHALL generate a personalized nutritional and behavioral review in Italian for periods of a week or longer, written in an empathetic and professional dietician persona. The review SHALL be based on food entry descriptions, consumption timing (timestamps), calorie density values (kcal per 100g), and logging provenance. The review SHALL NOT be generated if there is no food logged in the period.

#### Scenario: Successful weekly review generation
- **WHEN** the user requests a food report over a period of a week or longer and food entries exist
- **THEN** the system analyzes the entries and appends a personalized dietician review in Italian

#### Scenario: No food data for review
- **WHEN** a report is requested but no food entries exist in the period
- **THEN** the system does not attempt to generate a dietician review

### Requirement: Dietician review structured schema

The system SHALL enforce that the dietician review adheres to a structured format containing a warm summary, an energy density/volume insight, a temporal timing/regularity insight, a data sourcing/provenance quality insight, and a single practical actionable recommendation.

#### Scenario: Review conforms to schema
- **WHEN** the dietician review is generated
- **THEN** the output contains a general summary, a density insight, a timing pattern insight, a sourcing quality insight, and a single actionable tip, all in Italian

### Requirement: Dietician review reachable outside a report

The system SHALL be able to answer a user's question with a dietician review, not only append one to a requested report. A review produced this way SHALL satisfy every constraint that applies to a review appended to a report: the same structured format, the same basis in descriptions, timing, calorie density and provenance, and the same minimum period of a week or longer.

#### Scenario: Broad question about how eating has been going

- **WHEN** a user asks a broad question about their eating over a period of a week or longer, without requesting a report, and food entries exist in that period
- **THEN** the system may answer with a dietician review, in the same structured form as a review appended to a report

#### Scenario: Question about a period shorter than a week

- **WHEN** such a question concerns a period shorter than a week
- **THEN** the system does not generate a dietician review for it, and says what it would need instead of asserting a pattern

#### Scenario: No food logged in the period asked about

- **WHEN** such a question concerns a period in which no food was logged
- **THEN** the system does not generate a dietician review, consistent with the existing rule that a review is not generated without food data
