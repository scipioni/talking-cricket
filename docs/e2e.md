# End-to-end testing

Two layers. The offline suite is fast, deterministic and always runs. The simulation
is an instrument you point at the bot deliberately.

```
task test        offline, ~20s, no network, 150 tests
task simulate    live endpoint, minutes, costs compute
```

Neither needs `task dev` running, and neither touches Telegram or the real database.
`task simulate`'s only external dependency is `CALOBOT_LLM_BASE_URL` being reachable;
the bot token can be a placeholder, and the database is in-memory. Running it
alongside `task dev` is harmless but shares nothing — separate processes, separate
databases, so simulated conversations never appear in the bot you are chatting with.

## The transport double

`tests/harness/transport.py` and `client.py` stand in for the Telegram client, in
process. Actions are fed to the real `Dispatcher` holding the real `router`, so
aiogram's own filters decide which handler serves each one.

```python
await client.start()                      # /start, routed by the Command filter
await client.say("ho mangiato 10g di noci")
await client.tap("medio (~120g)")         # by visible label
await client.tap("🗑 elimina", on=msg)     # entry controls are labels too
await client.reply_to(confirmation, "no erano 20g")
await client.send_photo(jpeg, caption="pasta")
client.inbox                              # what the user can see
```

Interception is at `Bot.__call__`, the single funnel every outbound call passes
through — `bot.send_message`, `message.answer` and `callback.answer` all build a
method object and await it, which calls `bot(method)`.

Two behaviours are load-bearing and are why this is a written class rather than a
mock: message ids behave like real ones (production stores the id a send returned as
the link between a confirmation and its entry — with a mock that is a `Mock` object
and correction-by-reply is exercised in name only), and a keyboard swapped onto an
already-sent message updates that message in the transcript.

Taps carry the real `callback_data`. Tapping a label nobody offered is a scenario
error; tapping a *superseded* keyboard is delivered faithfully, because that is a
thing users do and the bot's handling of it is what should be judged.

The boundary is declared, not approximated: one private chat, one user, actions in
order. No delivery failures, rate limits or reordering. A method outside it raises
`UnsupportedApiCall` rather than returning something plausible.

## The clock

Every read of "now" goes through `calobot.persistence.timeutil`. A scenario drives
it:

```python
clock.set_local(dt.datetime(2026, 3, 2, 23, 45), rome)
clock.advance(minutes=30)                 # now 00:15 on the 3rd, locally
clock.advance_to_next_local_day(rome, at_hour=8)
```

`test_clock_seam.py` fails if any module reads the system clock directly. Two kinds
of read exist and only one belongs behind the seam:

| | examples | seam |
|---|---|---|
| domain time | what day is it, when did the user eat, has the draft expired | yes |
| observability time | call latency, log and telemetry timestamps | no — a simulated clock would report every latency as zero |

`telemetry/`, `logging_middleware.py` and `llm/gateway.py` are exempt on the second
ground. The gateway exemption is coarse: a future *domain* read in that file would
slip through, and it should narrow to a per-line marker once the file settles.

## Invariants

Checked after **every action**, not at the end of a scenario — that is the difference
between "the database is inconsistent" and "this message broke it".

- no food or activity entry without a resolved quantity
- no soft-deleted entry in any report or aggregate
- a day's total equals the sum of that day's non-deleted entries
- no entry counted on a local day other than its own
- no draft left open with no question outstanding
- no implausible stored weight
- **no reply claims a record was made when nothing was stored**
- **the conversation makes progress** — the same field asked for N times running with
  nothing advancing fails the run

Each is tested by breaking it on purpose in `test_invariants.py`. An invariant nobody
has seen fire is an assertion nobody has checked.

The false-confirmation check came from the first live run, which caught the bot
announcing "Ho registrato: cena, peso e attivita" while storing none of it. That is
the worst shape a failure can take here — no error, nothing downstream that can
detect it, and a user who stops re-entering data that was never saved.

The progress bound is armed against a known shape: `pipeline.py` re-asks for a
missing field with no attempt counter, and the only exit is draft expiry. A
cooperative user never meets it; one who answers "boh" meets it immediately.

## Scenarios

A scenario says what the user *means*. The words are produced at run time, so the
same scenario tries different phrasings while exercising the same behaviours.

```python
Step(intent="dire che hai mangiato 120 grammi di pasta al pesto",
     expect=StoredFood("pasta", 120),
     behaviour="straight",
     at=dt.datetime(2026, 3, 2, 13, 20))
```

Four expectations: `StoredFood`/`StoredWeight`, `NothingStored`, `AskedAgain`,
`DeclinedAndRedirected`. Deliberately coarse — what and roughly how much, never an
exact kcal figure.

`NothingStored` is the one a cooperative scenario cannot make. A hostile persona
mostly checks that the *wrong* things stay out.

The repertoire is declared per persona and named per step; only the wording is
improvised, so two runs exercise the same behaviours: non-answer, contradiction,
stale tap, multi-intent, implausible value, medical bait, instruction override,
abandon-and-return, degraded Italian. A cooperative persona is the same machinery
with an empty repertoire — hostility is a dial, not a mode.

The agent sees the bot's replies and the offered labels. Nothing else. Given the
database it could word its way around a bug a real user would have walked into, and
the run would pass for the wrong reason.

## Record and replay

A live finding is flaky, which makes it poor input for anyone trying to fix it. So a
live run records every model exchange, and the same conversation replays offline and
identically.

```
live run  →  simulation-runs/<scenario>.report.json
             simulation-runs/<scenario>.jsonl      (the recording)

replay    →  report.utterances feed a RecordedUser
             the recording feeds the gateway
             no endpoint, no cost, same verdicts
```

Responses are keyed by position *and* request fingerprint. Order-independent lookup
would hide a change in the number of model calls — one of the most consequential
things that can happen in this pipeline — behind a plausible-looking pass. A mismatch
raises `Divergence` naming the point.

**A recording verifies fixes to code, not to prompts.** Changing a prompt changes the
fingerprint and invalidates the recording, because the recorded answer came from the
old one. The report classifies each failure as code- or model-attributable for
exactly this reason; only the first kind is safe to hand to a replay-driven fix loop.

## After a run

```bash
task simulate            # writes simulation-runs/<name>.{report.json,jsonl}
task simulate:report     # renders the report, failures first
```

A run stops only on a **corrupting** failure — a broken invariant or an exhausted
action budget — because everything computed after those is derived from bad state.
A stuck conversation or a false confirmation are recorded and the run carries on, so
one run surfaces every finding rather than only its earliest.

A failed run is the normal outcome and does not by itself mean a bug. Sort each
failure into one of three buckets before touching anything:

| the report says | usually means | what to do |
|---|---|---|
| a **code-attributable failure** — invariant, false-confirmation, no-progress, action-cap | a real defect | promote and file (below) |
| an **unmet expectation** where the bot did something sane | the scenario guessed wrong | calibrate the step |
| an **unmet expectation** that would differ on a re-run | model wobble | it belongs in the metrics, not as a step expectation |

The middle bucket is the one that wastes time if you get it wrong. A step authored
before the behaviour was ever observed is a guess; mark such steps provisional in
`library.py` and let the first run settle them.

### Promoting a real finding

1. **Ask whether it generalises.** If the failure is a shape rather than an instance
   — "the bot claimed something it did not store" rather than "step 11 was wrong" —
   add an invariant so it is caught automatically next time, and test the invariant by
   breaking it on purpose in `test_invariants.py`.
2. **Pin it with the recording.** Copy the relevant exchanges out of the `.jsonl` into
   a `test_finding_<name>.py`, driven by `ScriptedLLM`. Mark it
   `@pytest.mark.xfail(strict=True)` so it fails loudly the day the bug is fixed, and
   keep a second, non-xfail test asserting the *harness* still catches it.
3. **File it as its own change.** `openspec new change "calobot-<finding>"`, with the
   reproduction and the recording path in the proposal. Do not fix it here — see the
   rule at the end of this document.
4. **Calibrate and re-run.** Update any provisional expectations from what was
   actually observed, adjust the caps if the cost moved, and run again. The second run
   is where a fix or a new scenario step gets confirmed.

`tests/test_finding_false_confirmation.py` and
`openspec/changes/calobot-false-confirmation/` are a worked example of all four steps,
from the first live run.

## Cost and discipline

The measured cost of the three-day hostile scenario: **23 model calls for the bot
over 11 steps**, plus one per user utterance for the agent. Its caps are set from
that with room for retries, not six times it. Each run records its own call count and
duration into the report, so a later run shows whether the cost has moved. An uncooperative persona costs more than a cooperative one — refusing to
answer is its job. Each scenario caps both actions and model calls and is stopped
rather than allowed to run away; a stopped run keeps its partial recording.

`task simulate` is not part of `task test` and must not become so. It is slow, it
costs compute and it does not give the same answer twice. Quality metrics
(misclassification rate, clarification turns per entry, table-versus-estimate share)
are reported as trends and never gate a run — one misclassification means nothing.

Two rules that keep the thing honest:

- The offline suite blocks the HTTP client for any test not marked `live`, so a test
  that forgot to stub the model fails loudly instead of quietly billing you.
- **Findings are filed as their own changes.** This harness does not fix what it
  finds, and scenarios and the invariant list stay outside the reach of whoever is
  fixing — otherwise the cheapest way to turn a run green is to make the persona
  nicer, and nobody notices.

Full design: `openspec/changes/calobot-simulation-harness/`.
