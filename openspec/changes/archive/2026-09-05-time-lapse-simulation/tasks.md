## 1. Harness vocabulary

- [x] 1.1 Add a `Silence` step type to `tests/harness/scenario.py` carrying an end instant and an originated-message expectation, with no intent, tap, behaviour or persona field; verify existing scenario imports and `task typecheck` still pass
- [x] 1.2 Add `NudgeArrived(kind)` and `NoNudge()` expectation dataclasses with `describe()` and extend the `Expectation` union; verify with a unit test asserting `describe()` renders in user-verifiable terms and mentions the kind where applicable

## 2. Nudge recognition

- [x] 2.1 Add a harness helper that classifies a `SentMessage` as a nudge via the stop-nudge keyboard (`decode_options`) and reads its kind by matching the stable first line of each template in `calobot.nudges.messages`; verify with a unit test composing one message per kind through `compose()` plus a plain reply that must not match
- [x] 2.2 Add run-timeline capture that delimits the shared `FakeBot` stream around actions and cycle executions so every sent message is attributed to its cause (action, or nudge-cycle execution at an instant); verify with a unit test interleaving a fake cycle call between two actions and asserting attribution and monotonic message ids

## 3. Driving the cycle as time advances

- [x] 3.1 Implement arithmetic crossing of `nudge_check_interval_seconds` execution points over each silent span and inter-action gap from the run's origin, invoking `run_nudge_cycle(fake_bot, settings)` once per point in order; verify with a unit test that a span of N days executes the expected number of cycles at the expected instants and none off-screen
- [x] 3.2 Score silence steps: at span end, apply `NudgeArrived`/`NoNudge` against the messages attributed to the span's executions, failing with kind, text and send instant in the report; verify with unit tests covering arrival, wrong-kind arrival and unexpected arrival
- [x] 3.3 Extend `RunReport` to show which jobs ran, when, and what each originated; verify by rendering a report for a scenario with a cycle execution and checking the fields appear in the rendered output and `to_dict()`

## 4. Temporal invariants

- [x] 4.1 Implement the database-checked invariants over the nudge send history — at most one nudge per `nudge_min_interval_days`, quiet hours at each send instant, no send while `nudges_enabled` is false or no-retention is on, none about a resolved advice record — and run them after every action and every cycle execution; verify with unit tests planting violating sends and asserting each is caught with the message named
- [x] 4.2 Add the timeline-based check that no nudge is originated after an opt-out earlier in the same run, fed by the enable/disable events recorded in 2.2; verify with a unit test replaying an enable → nudge → opt-out → silence sequence
- [x] 4.3 Wire the new invariants into the existing violation machinery so a violation fails the run regardless of the step's expectation and attributes to the causing action or execution; verify with a unit test where a step's own expectation passes but a temporal invariant fails and the run reports failed

## 5. Scenarios

- [x] 5.1 Add the fully offline multi-day scenario to the default suite: seeded user with nudges enabled, a streak of food entries and an old unresolved advice record; a silent span that expects a nudge; a conversational or command opt-out; further silence that expects none; verify it passes under `task test` with no network access
- [x] 5.2 Add a live multi-day scenario to the scenario library spanning several conversational logging days interleaved with silence, declaring its model-call budget; verify it runs explicitly like the other live scenarios and is excluded from the default suite
- [x] 5.3 Exercise the quiet-hours guard inside a scenario by choosing a run origin so an execution point lands inside the user's quiet hours and the invariant from 4.1 is what catches any send; verify the scenario passes with the current guards and fails if the quiet-hours check is temporarily disabled

## 6. Final verification

- [x] 6.1 Run `task check` (lint, typecheck, tests) and confirm the whole suite passes offline; confirm the default suite's runtime stays acceptable with the new scenario included
- [x] 6.2 Run `openspec validate --changes` and confirm the change still validates; re-read the delta spec scenarios against the implemented tests and note any divergence

## Notes from verification (6.1 / 6.2)

- Pre-existing on HEAD, unchanged by this work: 5 mypy errors (`ingestion/pipeline.py`, `telegram/handlers.py`), 74 ruff errors across unrelated files, and 2 failing/flaky tests (`test_memory_control.py::test_no_retention_persistence_survives_reloads`; `test_nudges.py::test_run_nudge_cycle_sends_when_opted_in_and_signal_fires` was wall-clock flaky and was pinned to the clock fixture here, since it blocks the suite in Rome evening/night hours).
- Spec-scenario mapping note: "A message follows silence / attributed to its local day" is exercised by the live `giulia-two-weeks` (entry attribution) and offline via the command step's instant; "No-retention suppresses nudges" is covered both by the invariant unit test and by the offline end-to-end `test_no_retention_suppresses_nudges_in_a_scenario`.
