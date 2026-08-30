## 1. Suppress the noise

- [x] 1.1 In the weight branch of the report path, emit the "no data" message only when
  `extraction.topic == "weight"` — verify a test asserts an unscoped report over a
  weight-less period contains no weight message
- [x] 1.2 In the activity branch, emit the "no data" message only when
  `extraction.topic == "activity"` — verify a test asserts an unscoped report over an
  activity-less period contains no activity message

## 2. Keep the direct answer

- [x] 2.1 Verify a scoped weight request over an empty period still says there is no
  data, with a test asserting the message is present
- [x] 2.2 Verify a scoped activity request over an empty period still says there is no
  data, with a test asserting the message is present

## 3. Guard the edges

- [x] 3.1 Verify an unscoped report over a period with nothing logged at all still
  produces exactly one message — the conversational empty-diary response — with a test
  asserting no weight or activity absence message accompanies it
- [x] 3.2 Verify an unscoped report where all three topics have data still reports all
  three, with a test asserting no section was lost
- [x] 3.3 Run `openspec validate quiet-empty-report-sections --strict` and `task check`,
  and confirm no new failures against the pre-change baseline
