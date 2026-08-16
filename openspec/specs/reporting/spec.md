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

A calorie report SHALL state the total energy consumed in the period, the daily average over the period, the daily budget it is measured against, and the difference between them. Days with no logged food SHALL be identified rather than counted as zero-calorie days in the average.

#### Scenario: Weekly calorie report

- **WHEN** a user asks for a weekly calorie report
- **THEN** the system reports the total, the daily average, the budget and the difference, and names the days with no logged food

#### Scenario: Period with no data at all

- **WHEN** a user asks for a report over a period in which nothing was logged
- **THEN** the system says there is no data for that period and produces no chart

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

An activity report SHALL state the total active minutes in the period, the number of days with recorded activity, and the total estimated energy expenditure, presented as information about movement and never as an adjustment to the calorie budget.

#### Scenario: Monthly activity report

- **WHEN** a user asks for an activity report over a month
- **THEN** the system reports the total active minutes, the days with activity and the total estimated expenditure

### Requirement: Charts

The system SHALL deliver reports over a week or longer as an image in the chat, accompanied by the textual figures. A weight chart SHALL show the individual measurements, a seven-day moving average, the goal as a reference line, and the projection when one exists. A calorie chart SHALL show the daily totals against the budget as a reference line. Charts SHALL render Italian text, including accented characters, correctly.

#### Scenario: Weekly report delivered as a chart

- **WHEN** a user asks for a report over a week or longer
- **THEN** the system sends an image of the chart together with the textual figures

#### Scenario: Daily report

- **WHEN** a user asks for a report over a single day
- **THEN** the system replies with the figures as text and does not send a chart

#### Scenario: Moving average with sparse data

- **WHEN** a weight chart covers a period with gaps between measurements
- **THEN** the moving average is drawn only where enough measurements exist to compute it, and gaps are not interpolated as if measured

### Requirement: Reports reflect only current data

Reports SHALL be computed from entries that are not deleted, using the Europe/Rome timezone for day boundaries.

#### Scenario: Day boundary

- **WHEN** an entry is recorded shortly before midnight Europe/Rome time
- **THEN** it is counted in that day and not in the following one
