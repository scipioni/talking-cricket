# reporting Specification

## Purpose

Turns the accumulated log into the thing the user actually came for: a visible trend. It defines which periods can be reported, what each report contains, and how charts are drawn so that normal day-to-day noise is not mistaken for progress or failure.

## Requirements

### Requirement: Report periods

The system SHALL produce reports over a day, a week, a month and a year, and SHALL default to the current period when the user does not state one.

#### Scenario: Report without a stated period

- **WHEN** a user asks for a report without saying which period
- **THEN** the system produces the report for the current day

#### Scenario: Period stated conversationally

- **WHEN** a user asks for a report using a conversational period such as "questo mese" or "l'ultima settimana"
- **THEN** the system produces the report for that period

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
### Requirement: Weight report contents

A weight report SHALL state the starting and ending weight of the period, the change over the period, the distance remaining to the goal, and a projected date of reaching the goal derived from the recent trend. The projection SHALL be omitted when the trend does not move towards the goal or when there are too few measurements to establish one.

#### Scenario: Weight report with an established trend

- **WHEN** a user asks for a weight report over a period containing enough measurements
- **THEN** the system reports the start, end, change, remaining distance and a projected date for reaching the goal

#### Scenario: Trend not moving towards the goal

- **WHEN** the recent trend is flat or moving away from the goal
- **THEN** the system omits the projection and says a projection is not currently possible

#### Scenario: Too few measurements

- **WHEN** the period contains too few weight measurements to establish a trend
- **THEN** the system reports what it has and states that more measurements are needed for a trend

### Requirement: Activity report contents

An activity report SHALL state the total active minutes in the period, the number of days with recorded activity, and the total estimated energy expenditure. For periods of a week or longer this remains purely informational about movement, with no adjustment to the calorie budget. For the day period, this same total energy expenditure figure is also the basis of the capped activity credit applied to that day's calorie report, per the Calorie report contents requirement.

#### Scenario: Monthly activity report

- **WHEN** a user asks for an activity report over a month
- **THEN** the system reports the total active minutes, the days with activity and the total estimated expenditure, with no effect on the calorie budget

### Requirement: Macro report contents

The system SHALL recognize a report request naming protein, fat, carbohydrate or fiber, or
their distribution collectively, as the `macros` topic, distinct from the `food` topic. A
macro report SHALL state, for each of protein, fat, carbohydrate and fiber, the total grams
consumed in the period and the daily average. Days with no logged food SHALL be identified
rather than counted as zero-gram days in the average, consistently with the calorie report.

The macro topic SHALL NOT be included when a report request does not name a topic; a user
must ask for macros specifically, the same way asking for weight or activity specifically
differs from an unscoped report.

#### Scenario: Macro distribution requested by name

- **WHEN** a user asks for "il grafico della distribuzione di proteine, grassi, carboidrati e
  fibre delle ultime 2 settimane"
- **THEN** the system classifies the request as the `macros` topic and reports total and
  daily-average grams of each of the four macros over that period, rather than falling back
  to a calorie report

#### Scenario: Macro report over a period with no logged food

- **WHEN** a user asks for a macro report over a period in which nothing was logged
- **THEN** the system states that there is no data for that topic in that period, per the
  existing rule for a topic named explicitly with no data

#### Scenario: Unscoped report does not include macros

- **WHEN** a user asks for a report without naming a topic
- **THEN** the report covers calories, weight and activity as before, and does not add a
  macro section

### Requirement: Charts

The system SHALL deliver reports over a week or longer as an image in the chat, accompanied by the textual figures. A weight chart SHALL show the individual measurements, a seven-day moving average, the goal as a reference line, and the projection when one exists. A calorie chart SHALL show the daily totals against the budget as a reference line. A macro report over a week or longer SHALL be delivered as a stacked bar chart showing each day's protein, fat, carbohydrate and fiber grams, one color per macro. Charts SHALL render Italian text, including accented characters, correctly.

#### Scenario: Weekly report delivered as a chart

- **WHEN** a user asks for a report over a week or longer
- **THEN** the system sends an image of the chart together with the textual figures

#### Scenario: Daily report

- **WHEN** a user asks for a report over a single day
- **THEN** the system replies with the figures as text and does not send a chart

#### Scenario: Moving average with sparse data

- **WHEN** a weight chart covers a period with gaps between measurements
- **THEN** the moving average is drawn only where enough measurements exist to compute it, and gaps are not interpolated as if measured

#### Scenario: Macro distribution chart over two weeks

- **WHEN** a user asks for a macro distribution report over two weeks
- **THEN** the system sends a stacked bar chart with one bar per day, each bar divided into
  the day's protein, fat, carbohydrate and fiber grams

### Requirement: Reports reflect only current data

Reports SHALL be computed from entries that are not deleted, using the Europe/Rome timezone for day boundaries.

#### Scenario: Day boundary

- **WHEN** an entry is recorded shortly before midnight Europe/Rome time
- **THEN** it is counted in that day and not in the following one

### Requirement: An unscoped report reports only the topics that have data

A report request that does not name a topic SHALL cover calories, weight and activity,
and SHALL report only those of them that have data in the period. An empty weight or
activity section of such a report SHALL NOT produce a message stating that the data is
absent, since the user asked for a report rather than about that topic.

When a report request names a topic, an empty result for that topic SHALL state that
there is no data for the period, because the user asked a direct question and silence
would not answer it.

This does not change what happens when nothing at all was logged in the period: the
calorie section runs for every unscoped request, so such a report still produces the
conversational empty-diary response and never falls silent.

#### Scenario: Unscoped report where only food was logged

- **WHEN** a user asks for a report without naming a topic, and the period holds logged
  food but no weight and no activity
- **THEN** the report presents the calorie information and says nothing about weight or
  activity

#### Scenario: Report scoped to a topic with no data

- **WHEN** a user asks specifically about their weight or their activity over a period
  in which none was logged
- **THEN** the system states that there is no data for that topic in that period

#### Scenario: Unscoped report over a period with nothing logged

- **WHEN** a user asks for a report without naming a topic over a period in which
  nothing at all was logged
- **THEN** the system still responds with the conversational empty-diary response, and
  does not additionally report the absence of weight and activity

#### Scenario: Unscoped report where every topic has data

- **WHEN** a user asks for a report without naming a topic and all three topics have
  data in the period
- **THEN** all three are reported, as before
