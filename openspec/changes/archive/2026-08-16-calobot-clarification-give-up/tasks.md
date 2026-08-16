## 1. Counting attempts

- [x] 1.1 Store a per-draft attempt count in the existing draft payload, treating a missing key as zero so drafts written before this change stay valid
- [x] 1.2 Increment the count when a reply cannot be used to fill the field being asked about
- [x] 1.3 Reset the count as soon as the draft advances, whether by resolving the field or by moving to the next item
- [x] 1.4 Add a test that the count survives a reload of the draft, as the draft itself does
- [x] 1.5 Add a test that a successful answer followed by a later hard field starts the count again rather than carrying it over

## 2. Bounded asking and give-up

- [x] 2.1 Stop asking once the count reaches the configured limit
- [x] 2.2 Discard the draft through the existing path and store nothing
- [x] 2.3 Reply naming the entry that was not recorded and inviting the user to send it again
- [x] 2.4 Assert in code and in tests that no value is inferred to complete a draft the user did not complete
- [x] 2.5 Add a test that the exchange from the live run — three unusable answers to the same portion question — now ends instead of looping
- [x] 2.6 Add a test that a zero quantity, which reaches this loop since `calobot-false-confirmation`, is also bounded by it

## 3. One assembly point, varied wording

- [x] 3.1 Route every clarification message through one helper that takes the clarification and the attempt count
- [x] 3.2 Move the existing call sites onto it, leaving no other place that builds a clarification message
- [x] 3.3 Vary the wording by attempt from a fixed rotation, with no model call
- [x] 3.4 Keep offering the tappable options on every ask, which the current code already does
- [x] 3.5 Add a test that consecutive asks for the same field differ from one another
- [x] 3.6 Add a test asserting the rotation cannot be exhausted before the limit is reached

## 4. The visible way out

- [x] 4.1 Offer an abandon option among the clarification's tappable options
- [x] 4.2 Match it as an exact sentinel before the answer is parsed, so it can never be read as a quantity
- [x] 4.3 On abandonment, discard the draft, store nothing, and confirm that nothing was recorded
- [x] 4.4 Add a test that abandoning leaves no entry and no open draft
- [x] 4.5 Add a test that the sentinel is not a plausible answer to any clarification the system asks

## 5. Configuration and the harness relationship

- [x] 5.1 Add the attempt limit as a configurable setting with a default, alongside the draft expiry setting
- [x] 5.2 Document it in `.env.example` and the README's configuration list
- [x] 5.3 Verify the production limit is not looser than the harness's progress bound, or correct give-up behaviour would fail every simulation run
- [x] 5.4 Add a test that pins that relationship, so changing either value alone fails

## 6. Verification

- [x] 6.1 Run the offline suite, lint and typecheck
- [x] 6.2 Re-run the live scenario and confirm the day-two stall no longer occurs
- [x] 6.3 Confirm the harness's `no-progress` invariant does not fire on the corrected behaviour
- [x] 6.4 Update the persona's non-answer steps if the scenario now ends the draft earlier than the steps assume
