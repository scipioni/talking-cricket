## 1. A quantity must be valid, not merely present

- [x] 1.1 Make food quantity resolution treat a non-positive grams value as unresolved rather than as an answer
- [x] 1.2 Make activity duration resolution treat a non-positive minutes value as unresolved, which has the same null-check shape
- [x] 1.3 Apply the same rule to a quantity supplied by the user through the clarification loop, whether tapped or typed as free text
- [x] 1.4 Verify a rejected quantity enters the existing clarification loop rather than producing an error with nowhere to go
- [x] 1.5 Add a test that no path stores a food or activity entry with a non-positive quantity
- [x] 1.6 Add a test that "0 grammi" typed as a clarification answer re-asks instead of storing

## 2. The classifier's self-contradiction routes the message

- [x] 2.1 Treat a conversational classification that also reports ignored loggable text as a contradiction, and handle the message as a log
- [x] 2.2 Leave the common path untouched: a conversational message with no ignored text still gets a conversational reply and no extra model call
- [x] 2.3 Handle the case where re-handling finds nothing extractable after all, falling back without storing anything
- [x] 2.4 Add a test driven by the recorded run-1 classification, asserting the meal is extracted rather than answered conversationally
- [x] 2.5 Add a test that an ordinary greeting still costs exactly one classification and one reply

## 3. The claim guard

- [x] 3.1 Implement detection of a reply asserting that something was recorded, independently of the harness implementation
- [x] 3.2 Comment the deliberate duplication, so the harness detector and this one are not later merged into one
- [x] 3.3 Apply the guard only when the turn stored nothing, leaving every real confirmation untouched
- [x] 3.4 Replace an offending reply wholesale rather than editing it, with a message that says nothing was recorded and invites the user to restate
- [x] 3.5 Log when the guard fires, so a mis-route that reaches the backstop is visible in production rather than only in a simulation
- [x] 3.6 Add a test using the recorded run-1 reply verbatim, asserting the claim never reaches the user
- [x] 3.7 Add a test that a conversational reply making no claim is sent unchanged
- [x] 3.8 Add a test that a genuine confirmation after a real write is not examined or altered

## 4. Instructions in content

- [x] 4.1 Confirm by test that the recorded injection now stores nothing, without any code that recognises the message as an attack
- [x] 4.2 Add a test that an instruction to bypass a safety limit leaves that limit in force
- [x] 4.3 Add a test that a message mixing an instruction with a genuine log still records the log

## 5. Close the findings

- [x] 5.1 Remove the xfail marker from the false-confirmation regression test and confirm it passes
- [x] 5.2 Confirm the harness invariants for false confirmation and for entries without a quantity no longer fire on the recorded cases
- [x] 5.3 Run the offline suite, lint and typecheck
- [x] 5.4 Re-run the live scenario and confirm the two findings are gone, noting that the recording is invalidated if any prompt changed
- [x] 5.5 Record in the run report whether `marco-three-days` now reaches day three, which it has never done
