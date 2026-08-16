## Context

See `proposal.md` — Why for motivation, and `specs/test-transport` and `specs/conversation-simulation` for the behaviour.

Three facts about the existing code shape everything below.

The handler layer is not a thin adapter. `telegram/handlers.py` owns onboarding advancement, the deterministic application of onboarding button taps, entry controls, reply-to targeting, and the sequence that sends a confirmation, records its message identifier against the entry, and then swaps its keyboard for entry controls. `MessagePipeline` sees none of this. Anything driving only the pipeline is driving less than half the product.

The one existing callback test uses an `AsyncMock` bot, which makes `sent.message_id` a mock object. It is written into the database as the confirmation identifier, so the reply-to correction path is exercised in name only.

The existing end-to-end tests stub the model with an ordered `side_effect` list, which couples every test to the exact number and order of model calls. That coupling is the thing to avoid reproducing at a larger scale.

## Goals / Non-Goals

**Goals:**

- Make every user-reachable path drivable from a test without a branch in production code that exists only for tests.
- Give a failure a single, reproducible artefact, so the agent that fixes it never needs the machine that found it.
- Keep the offline suite offline, fast and deterministic, while the live suite is explicit and budgeted.

**Non-Goals:**

- Refactoring the handler layer into a transport-agnostic service. Considered and rejected below.
- Building a general Telegram emulator. Only what the bot actually calls.
- Making the live run a gate. It is an instrument.

## Decisions

### Drive the real handlers through a written double, not a mock and not a refactor

Three options were live:

```
  A  AsyncMock bot                B  extract a service layer      C  written double
     (what exists today)             below the handlers

     zero work                       clean, permanently             ~one file, test-only
     message ids are mocks           testable                       real message ids
     transcript lives in             handlers become thin           transcript is the point
       call_args                     BUT: refactors the             production untouched
     can't see buttons               highest-risk file, and
                                     message identity is
                                     inherently transport-shaped
```

C is chosen. B is the better long-term architecture and may still be right later, but doing it *first* means refactoring the file with the most known-bug history while having no way to test the refactor — the harness that would catch a regression is the thing being built. C gets that harness in place. If B happens afterwards, the harness proves it.

The double is a written class rather than a mock because two of its behaviours are load-bearing and a mock cannot supply them: assigning identifiers that behave like real message identifiers, and reflecting a later keyboard replacement onto the message it replaced. Both are exactly what the correction paths depend on.

### Taps are addressed by label and travel as real action data

The double decodes each outgoing keyboard back into label-to-data pairs and keeps them against the message. A scenario taps a label; the double sends the underlying data through the production callback handler.

This is what removes the fake path in today's tests, where a button answer is fed back as if the user had typed the label. That shortcut works only because the clarification loop happens to accept the label as free text, and it means the real callback handler is untested for food and activity. Addressing by label also keeps scenarios readable and makes a tap on a label nobody offered a scenario error rather than a silent pass.

Deliberately *not* rejected: tapping a superseded keyboard. That is a real thing users do and one of the adversary's tools, so the double delivers it faithfully and lets the bot's own handling be what is judged.

### A ledger of intent, not a transcript and not a judge

The simulated user is scripted in *meaning* and free in *expression*. Each step carries a machine-readable intent; the agent renders it into Italian; the oracle compares the intent against the database.

The alternative — let the agent converse freely and have a second model judge whether the conversation went well — was rejected. It replaces a cheap deterministic comparison with an expensive non-deterministic one, and it makes every failure arguable. A run must be able to fail without anyone reading it.

The consequence worth stating: this harness cannot discover intents nobody wrote down. It stresses known behaviours hard, rather than exploring. Exploration is a later dial (see Open Questions), not this version.

### Adversarial behaviours are declared; only the wording is improvised

A scenario names which hostile behaviour each step exercises — non-answer, contradiction, stale tap, multi-intent, implausible value, medical bait, instruction override, abandonment, degraded Italian. The agent invents the words.

This keeps runs comparable: two runs of the same scenario exercise the same behaviours, so a difference in outcome is a difference in the system, not in the dice. Fully model-invented hostility finds things nobody anticipated but cannot be re-run, which makes it useless as the input to a fixing loop — the priority here.

Hostility is a per-persona dial rather than a mode, so a cooperative persona is the same machinery with an empty repertoire. The personas shipped with this change are hostile.

### Invariants are evaluated after every action, not at the end

Checking at the end of a scenario tells you a database is inconsistent; checking after every action tells you which message made it so. The cost is a handful of queries per turn against an in-memory database, which is nothing next to a model call.

The invariant most likely to fire first is the progress bound. Today, when the clarification loop cannot use an answer, it re-asks the same question (`pipeline.py:139-153`); there is no attempt counter, and the only exit is draft expiry. A cooperative user never sees this. A persona that answers "boh" repeatedly hits it immediately. That this is predictable is a feature: it is the harness's first self-test. Per the proposal, this change reports it and does not fix it.

### Recordings are ordered, and divergence is an error

A recording is the ordered sequence of model requests and responses. Replay walks it in order and checks that each request still corresponds to what was recorded; a mismatch stops the replay and reports where.

Keying responses by a hash of the request instead, so order stops mattering, was rejected. A change in the *number* of model calls is one of the most consequential things that can happen in this pipeline, and order-independent lookup hides it behind a plausible-looking pass. The existing `side_effect` tests are brittle for exactly this reason — the fix is to make the divergence loud and legible, not to make it invisible.

The honest limitation: a recording verifies fixes to code, not fixes to prompts. Changing a prompt invalidates the recording, because the recorded response was produced by the old one. So the report must classify each failure as code-attributable or model-attributable, and only the first kind is safely handed to a replay-driven fixing loop.

### One clock, injected

Every read of the current instant goes through a single seam, and the simulation supplies the scenario's instant. Patching `utcnow` per importing module was rejected: it is imported by name in several places, so the patch set is a list that silently rots as modules are added, and a missed one produces a scenario that half-travels in time — the worst possible failure for a test harness.

Day boundaries already take a timezone as a parameter, so this is the last piece needed to make midnight, week starts and draft expiry testable.

### Findings do not fix themselves

Anything the harness finds becomes its own change. The scenario definitions and the invariant list are outside the fixing agent's edit scope. This is not process hygiene: the cheapest way to turn a hostile run green is to make the persona nicer, and a fixing agent optimising for green will find that before it finds the bug.

## Risks / Trade-offs

- **The double drifts from real Telegram behaviour** → It emulates only what the bot calls, and its fidelity boundary is stated as a requirement rather than assumed. Anything outside it has no way to be expressed, so a passing run cannot quietly mean less than it appears to.
- **Live runs are expensive and an adversary makes them more so** → Per-scenario caps on actions and on model calls, enforced rather than advisory, and a stopped run keeps its recording.
- **A hostile persona produces failures that are wording disputes, not bugs** → Expectations are coarse by construction: a stored entry is checked for what and roughly how much, never for an exact energy value, and refusals are checked for redirection rather than for phrasing.
- **The harness becomes a second system to maintain** → It shares the existing in-memory session fixture and the existing gateway, and the offline half of it is used by the ordinary suite too, so it is not carried by the live runs alone.
- **Recordings accumulate and go stale** → Only recordings promoted to regression tests are kept; the rest are run artefacts. A stale one announces itself as a divergence rather than passing wrongly.
- **The agent works around a bot failure without noticing it** → The observation boundary is a requirement: the agent sees the transcript and nothing else.

## Migration Plan

Additive and test-only, with one exception: the clock seam changes production call sites without changing behaviour. It is the one piece that touches running code, so it ships on its own — after the transport double, which needs nothing from it, and before the first scenario that spans more than one day — and is verified by the existing suite rather than by the harness it enables.

The two existing tests that fake a button tap or mock the bot are rewritten onto the double as part of the transport work, not left in place — leaving both would mean two ways to test the same path and a slow drift back to the weaker one.

There is nothing to roll back. Removing the harness removes test capability and no runtime behaviour.

## Open Questions

- How many consecutive unusable answers constitute a non-progressing conversation. A constant, tunable once real runs show what a hostile persona actually produces.
- Whether the simulated user should run on the same model as the bot. The same model is simplest and cheapest; a different one risks the agent and the bot sharing blind spots, which is an argument for varying it later.
- Whether metrics are persisted across runs for trend comparison, or printed per run and compared by hand until there are enough runs for a trend to mean anything.
- Whether a later mode lets the agent improvise behaviours outside the declared repertoire, as an exploratory pass whose findings are then written down as ordinary scenarios. Additive to this design; deliberately not in this version.
