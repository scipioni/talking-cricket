## MODIFIED Requirements

### Requirement: Calorie report contents

A calorie report SHALL state the total energy consumed in the period, the daily average over the period, the daily budget it is measured against, and the difference between them. Days with no logged food SHALL be identified rather than counted as zero-calorie days in the average. For reports covering a week or a month, the report SHALL also include a personalized dietician review in Italian summarizing behavioral, density, and timing observations.

#### Scenario: Weekly calorie report
- **WHEN** a user asks for a weekly calorie report
- **THEN** the system reports the total, the daily average, the budget, the difference, and names the days with no logged food, and appends a personalized dietician review in Italian

#### Scenario: Period with no data at all
- **WHEN** a user asks for a report over a period in which nothing was logged
- **THEN** the system says there is no data for that period and produces no chart or dietician review
