## MODIFIED Requirements

### Requirement: Calorie report contents

A calorie report SHALL state the total energy consumed in the period, the daily average over the period, the daily budget it is measured against, and the difference between them. Days with no logged food SHALL be identified rather than counted as zero-calorie days in the average. For reports covering a week or a month, the report SHALL also include a personalized dietician review in Italian summarizing behavioral, density, and timing observations.

For the **day** period only, the budget used for the difference SHALL be increased by an activity credit: a fixed fraction of that day's logged activity kcal (per the Activity report), capped at a fixed absolute maximum, so that a day with substantial extra exercise is not reported as a larger shortfall than it is. The report text SHALL state the credited amount whenever it is non-zero, so the effective budget is never silently different from the profile's stated daily budget. Week, month and year calorie reports SHALL continue to compare against the unmodified daily budget (or its multi-day average), with no activity credit applied.

A day-period calorie report SHALL also include a short advice line for the rest of the day, informed by the (activity-credited) remaining calories for the day and a qualitative read of whether the food logged so far leans toward one macronutrient group, worded so as to nudge toward balance without stating a specific macronutrient gram amount the system does not track. This advice SHALL NOT be generated when there is no food logged that day.

When a user asks for a report over a period in which nothing was logged, the system SHALL respond conversationally, addressing the user's query while stating that the diary is empty for that period. For daily empty reports, the conversational response SHALL acknowledge the user's full remaining calorie budget. It SHALL NOT produce charts or a dietician review.

#### Scenario: Weekly calorie report

- **WHEN** a user asks for a weekly calorie report
- **THEN** the system reports the total, the daily average, the budget, the difference, and names the days with no logged food, and appends a personalized dietician review in Italian

#### Scenario: Period with no data at all

- **WHEN** a user asks for a report over a period in which nothing was logged
- **THEN** the system responds conversationally indicating that the diary is empty (e.g. acknowledging the full remaining budget for a daily query) and produces no chart or dietician review

#### Scenario: Daily report on a day with logged activity

- **WHEN** a user asks for a daily calorie report on a day where activity was also logged
- **THEN** the difference is computed against the daily budget increased by the capped activity credit for that day, and the report states the credited amount

#### Scenario: Daily report on a day with no logged activity

- **WHEN** a user asks for a daily calorie report on a day with no logged activity
- **THEN** the difference is computed against the unmodified daily budget, exactly as before this change

#### Scenario: Weekly report on a week that includes an active day

- **WHEN** a user asks for a weekly calorie report covering a day that had logged activity
- **THEN** the week's difference is computed against the unmodified daily budget average, with no activity credit applied

#### Scenario: Daily report includes rest-of-day advice

- **WHEN** a user asks for a daily calorie report and food was logged that day
- **THEN** the report includes a short rest-of-day advice line reflecting the remaining credited calories and a qualitative nudge toward macronutrient balance

#### Scenario: Daily report with no food logged

- **WHEN** a user asks for a daily calorie report on a day with no food logged
- **THEN** no rest-of-day advice is generated
