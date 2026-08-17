## Purpose

Generates personal, clinical, and encouraging behavioral dietician reviews in Italian by analyzing the user's calorie densities, meal timing, and logging habits over a week or a month.

## ADDED Requirements

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
