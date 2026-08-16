## 1. Transport double

- [x] 1.1 Implement the outgoing side: record every message sent with its text, a unique identifier, its attached options and whether it carried an image
- [x] 1.2 Assign message identifiers that behave as real ones, so the identifier stored against a confirmed entry is the identifier of the message that was sent
- [x] 1.3 Reflect a later replacement of a message's controls onto that message in the transcript
- [x] 1.4 Decode outgoing keyboards into label-to-action pairs and keep them against the message that offered them
- [x] 1.5 Accept the remaining calls the handlers make, including the typing indicator and callback acknowledgement, without them affecting the transcript's meaning
- [x] 1.6 Add a test asserting the transcript reflects a confirmation whose controls were swapped after sending

## 2. Inbound actions

- [x] 2.1 Deliver a text message through the production text handler
- [x] 2.2 Deliver a command through its production handler, covering `/start`, `/annulla`, `/profilo` and `/cancellami`
- [x] 2.3 Deliver a tap on an inline option, addressed by visible label, carrying the real action data through the production answer-callback handler
- [x] 2.4 Deliver a tap on an entry control through the production entry-control handler
- [x] 2.5 Deliver a message sent as a reply to an earlier message, carrying the identity of the message it answers
- [x] 2.6 Deliver a photo with an optional caption through the production photo handler
- [x] 2.7 Report a tap on a label offered by no message in the transcript as a scenario error, and add a test for it
- [x] 2.8 Deliver a tap on a superseded keyboard faithfully rather than rejecting it, and add a test asserting the bot's own handling is what is observed
- [x] 2.9 Verify no production code contains a branch that exists only for the double

## 3. Existing tests rebased

- [x] 3.1 Rewrite the food clarification tests to tap the offered option instead of feeding its label back as text
- [x] 3.2 Rewrite the onboarding callback tests onto the double, removing the mocked bot
- [x] 3.3 Add a test covering correction by reply that fails if the confirmation identifier is not a real message identifier
- [x] 3.4 Add a test covering deletion through the entry control, asserting the entry is soft-deleted and absent from reports
- [x] 3.5 Confirm the whole suite still passes offline and without network access

## 4. Clock seam

- [x] 4.1 Route every read of the current instant through a single injectable seam
- [x] 4.2 Move all existing callers onto it, leaving no direct reads
- [x] 4.3 Add a guard test that fails if a new direct read of the system clock is introduced
- [x] 4.4 Let a scenario set and advance the instant, including across a local day boundary in the configured timezone
- [x] 4.5 Verify the existing suite passes unchanged, since this task alters no behaviour

## 5. Invariants

- [x] 5.1 Implement the invariant set: no entry without a resolved quantity, no soft-deleted entry in any aggregate, day totals equal the sum of that day's non-deleted entries, no draft open with no question outstanding, no entry attributed to the wrong local day
- [x] 5.2 Evaluate the set after every inbound action and attribute a violation to the action that caused it
- [x] 5.3 Implement the progress bound: fail when the same missing field is asked for more than the configured number of consecutive times without the draft advancing
- [x] 5.4 Implement the action cap per scenario, stopping and reporting rather than continuing
- [x] 5.5 Make an invariant violation fail the run even when the step's own expectation is met
- [x] 5.6 Add tests that deliberately violate each invariant and assert it is caught and correctly attributed

## 6. Scenarios and the ledger

- [x] 6.1 Define a scenario as ordered steps carrying a simulated instant, an intent, a declared behaviour and an expectation
- [x] 6.2 Implement the four expectation types: entry stored, nothing stored, asked again, declined and redirected
- [x] 6.3 Make the stored-entry expectation coarse — what, roughly how much, which local day — and never an exact energy value
- [x] 6.4 Implement the oracle that scores each step against the persisted state and the conversation, with no human reading required
- [x] 6.5 Record for each step the intent, the words sent, the replies received and the relevant persisted state
- [x] 6.6 Add tests for the oracle itself, including a step that should fail and one whose expectation is that nothing is stored

## 7. Simulated user

- [x] 7.1 Render a step's intent into plausible Italian through the existing gateway, varying wording between runs
- [x] 7.2 Restrict the agent's observation to outgoing messages and currently offered options, and add a test asserting it receives nothing else
- [x] 7.3 Let the agent react to an unanticipated clarification according to its persona rather than failing the scenario
- [x] 7.4 Implement the declared repertoire: non-answer, contradiction and self-correction, stale tap, several intents in one message, implausible value, insistence on individual medical advice, instruction override, abandonment and return, degraded Italian
- [x] 7.5 Record which behaviour each step exercised, so two runs of a scenario are comparable
- [x] 7.6 Make hostility a per-persona dial, with a cooperative persona being the same machinery with an empty repertoire
- [x] 7.7 Author the first hostile persona and a three-day food-logging scenario

## 8. Recording and replay

- [x] 8.1 Record every model request and response in order during a live run
- [x] 8.2 Replay a recording with no network access, producing the same conversation and the same verdicts
- [x] 8.3 Detect a request that does not correspond to the recording, stop, and report the point of divergence
- [x] 8.4 Enforce the per-scenario model call cap, keeping the partial recording when it is reached
- [x] 8.5 Keep the default test command offline, and add a test asserting no scenario in it contacts the endpoint
- [x] 8.6 Add a test that a changed call sequence produces a reported divergence rather than a pass or a misleading failure

## 9. Run report

- [x] 9.1 Produce a per-step verdict and a run summary
- [x] 9.2 Classify each failure as attributable to the code under test or to the model's judgement
- [x] 9.3 Include everything needed to reproduce a failure without the original run: scenario, persona, seeded state, conversation, persisted state, recording
- [x] 9.4 Report the quality metrics — unintended classifications, clarification turns per stored entry, table versus estimate share — without letting them fail a run
- [x] 9.5 Verify a report alone is sufficient by replaying a failure from it in a fresh checkout

## 10. First live run

- [x] 10.1 Run the hostile three-day food scenario against the real endpoint and record it
- [x] 10.2 Confirm the progress bound fires on repeated unusable answers, and file the finding as its own change rather than fixing it here
- [x] 10.3 Promote at least one code-attributable finding into a permanent regression test driven by its recording
- [x] 10.4 Measure the cost and duration of a hostile run and set the default caps from it
- [x] 10.5 Document how to invoke a live run, what it costs, and why it is not part of the default suite
