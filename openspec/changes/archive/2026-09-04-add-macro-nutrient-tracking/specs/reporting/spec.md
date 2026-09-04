## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Charts

The system SHALL deliver reports over a week or longer as an image in the chat, accompanied
by the textual figures. A weight chart SHALL show the individual measurements, a seven-day
moving average, the goal as a reference line, and the projection when one exists. A calorie
chart SHALL show the daily totals against the budget as a reference line. A macro report
over a week or longer SHALL be delivered as a stacked bar chart showing each day's protein,
fat, carbohydrate and fiber grams, one color per macro. Charts SHALL render Italian text,
including accented characters, correctly.

#### Scenario: Weekly report delivered as a chart

- **WHEN** a user asks for a report over a week or longer
- **THEN** the system sends an image of the chart together with the textual figures

#### Scenario: Daily report

- **WHEN** a user asks for a report over a single day
- **THEN** the system replies with the figures as text and does not send a chart

#### Scenario: Moving average with sparse data

- **WHEN** a weight chart covers a period with gaps between measurements
- **THEN** the moving average is drawn only where enough measurements exist to compute it,
  and gaps are not interpolated as if measured

#### Scenario: Macro distribution chart over two weeks

- **WHEN** a user asks for a macro distribution report over two weeks
- **THEN** the system sends a stacked bar chart with one bar per day, each bar divided into
  the day's protein, fat, carbohydrate and fiber grams
