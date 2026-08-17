## ADDED Requirements

### Requirement: Dietician review reachable outside a report

The system SHALL be able to answer a user's question with a dietician review, not only
append one to a requested report. A review produced this way SHALL satisfy every
constraint that applies to a review appended to a report: the same structured format,
the same basis in descriptions, timing, calorie density and provenance, and the same
minimum period of a week or longer.

#### Scenario: Broad question about how eating has been going

- **WHEN** a user asks a broad question about their eating over a period of a week or
  longer, without requesting a report, and food entries exist in that period
- **THEN** the system may answer with a dietician review, in the same structured form
  as a review appended to a report

#### Scenario: Question about a period shorter than a week

- **WHEN** such a question concerns a period shorter than a week
- **THEN** the system does not generate a dietician review for it, and says what it
  would need instead of asserting a pattern

#### Scenario: No food logged in the period asked about

- **WHEN** such a question concerns a period in which no food was logged
- **THEN** the system does not generate a dietician review, consistent with the
  existing rule that a review is not generated without food data
