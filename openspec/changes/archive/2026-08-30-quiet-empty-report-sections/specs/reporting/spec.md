## ADDED Requirements

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
