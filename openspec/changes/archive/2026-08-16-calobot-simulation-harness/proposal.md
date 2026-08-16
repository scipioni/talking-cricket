## Why

Calobot's risk lives almost entirely in judgement the code does not control: whether the model classifies "stasera ho spizzicato" as food, picks the right table row, or asks the right clarifying question. The current suite cannot see any of it, because `tests/test_pipeline_e2e.py` stubs *both* sides of every exchange — the user's words are hardcoded strings and the model's replies are hardcoded JSON in exact call order. It verifies that the pipe is connected, not that anything sensible flows through it.

It also cannot reach the half of the product a real user spends most of their time in. Buttons, entry controls, corrections-by-reply, onboarding and the commands all live in `telegram/handlers.py`, above `MessagePipeline`, and nothing drives them. The one test that does (`tests/test_onboarding_callback.py`) uses an `AsyncMock` bot, so `sent.message_id` is a mock object — which means the confirmation-message-to-entry link that makes reply-corrections work is written but never exercised. The food tests fake a button tap by feeding the button's *label* back as text, a path no real client takes.

This change builds the missing transport double, then an adversarial simulated user that drives it against the real language model over simulated days, and turns each live finding into a cheap deterministic regression test.

## What Changes

- **In-process Telegram double**: a fake `Bot` that assigns real message ids, records everything sent, and decodes outgoing keyboards back into tappable options; plus a client façade offering `say`, `tap`, `reply_to`, commands and an inbox. Taps travel as the real `callback_data` through the real handlers, so `on_answer_callback` and `on_entry_control_callback` become reachable for the first time.
- **Existing tests rebased onto it**: the label-as-text shortcut in `test_pipeline_e2e.py` is replaced by a real tap, and `test_onboarding_callback.py` moves off `AsyncMock`.
- **Controllable clock**: day-boundary and expiry logic reads the current instant through an injectable clock rather than a bare `utcnow()`, so a scenario can advance days, cross midnight in `Europe/Rome`, and expire a draft on demand.
- **Adversarial simulated user**: a language-model agent that renders a structured intent into messy, uncooperative Italian and reacts to what it is shown. It observes only outgoing text and available buttons — never the database. Hostility is a per-persona dial; the personas shipped here are hostile by default.
- **Intent ledger and oracle**: every scenario step carries a machine-readable expectation — entry stored, nothing stored, asked again, or refused — and the run is scored by diffing the ledger against the database. No human reads transcripts to find out whether a run passed.
- **Hard invariants checked after every turn**: violations that are bugs regardless of model wording, including entries stored without a resolved quantity, soft-deleted entries surfacing in reports, day totals disagreeing with their entries, orphaned drafts, and a conversation that fails to make progress within a bounded number of turns.
- **Quality metrics reported, never gated**: misclassification rate, clarification turns per logged entry, table-versus-estimate share. Reported as trends across runs.
- **Record and replay**: a live run records every gateway call and response to a cassette; the same transcript replays deterministically and for free against that cassette, so a fixing agent can iterate, and the cassette graduates into a permanent regression test of the shape already used in the suite.
- **Budget and turn caps**: each scenario declares a maximum number of turns and model calls, and is aborted and reported rather than allowed to run away.

Explicitly **out of scope**: fixing any bot behaviour this harness finds — findings become their own changes; running against the live model in CI; simulating photo input, which needs a fixture corpus and belongs with `calobot-photo-input`; simulating Telegram delivery failures, rate limits or network faults; multi-user or concurrency scenarios.

## Capabilities

### New Capabilities

- `test-transport`: the in-process Telegram double — faithful message identity, keyboard round-tripping so a tap carries real callback data, entry-control and reply-to addressing, an observable transcript, and the boundary of what it does and does not emulate.
- `conversation-simulation`: scenario and persona definition, the adversarial agent's observation boundary and repertoire, the intent ledger and its expectation types, hard invariants versus reported metrics, turn and budget caps, cassette recording and replay fidelity, and the run report a fixing agent consumes.

### Modified Capabilities

None. This change adds testing capability and deliberately does not alter observable bot behaviour; anything it finds is filed as a separate change so that the tool and the fixes it motivates stay independently reviewable.

## Impact

- **New components**: a test-only transport package and a simulation package, neither imported by the running bot.
- **Modified components**: `persistence/timeutil.py` gains a clock seam and its callers move to it — the only production code this change touches. `tests/test_pipeline_e2e.py` and `tests/test_onboarding_callback.py` are rewritten onto the transport double.
- **New dependencies**: none at runtime. The simulated user reuses the existing `LLMGateway` rather than adding a client.
- **Cost and latency**: a live run makes real calls to the configured endpoint, and an adversarial persona makes materially more of them than a cooperative one — this is why turn and budget caps are part of the capability rather than an afterthought. Live runs are invoked explicitly and are not part of `task test`.
- **Separation of duties**: the agent that runs simulations and the agent that fixes findings are distinct, and scenario definitions and the invariant list are outside the fixing agent's edit scope — otherwise the cheapest way to turn a run green is to weaken the test.
- **Privacy**: scenarios are synthetic. No real user conversation is recorded into a cassette.
