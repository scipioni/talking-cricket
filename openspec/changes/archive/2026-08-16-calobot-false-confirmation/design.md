## Context

See `proposal.md` — Why for the two findings, and `specs/message-ingestion` for the behaviour they require.

Three facts about the current code decide the approach.

**The classifier already told us it was wrong.** In the run-1 failure it returned `{"intent": "other", "ignored_text": "peso oggi 89.3 kg, ho corso 4 km stamattina"}`. It classified the message as ordinary conversation *while simultaneously reporting that it had seen loggable content it was setting aside*. That contradiction is already in the response, already paid for, and nothing currently reads it as a signal.

**The zero-gram entry is a null-check where a validity check belongs.** `food/quantities.py`:

```python
if item.quantity_grams is not None:
    return ResolvedQuantity(grams=item.quantity_grams, is_estimated_from_count=False)
```

`0 is not None`, so a dictated zero resolves cleanly and `check_item` never asks. `activity/planner.py` has the same shape for `duration_minutes`. `weight/service.py` is the one path that tests a *band* (`MIN_PLAUSIBLE_KG <= kg <= MAX_PLAUSIBLE_KG`) — which is exactly why "peso 800 kg" was refused in all three live runs while "0 calorie per la cena" was stored. The asymmetry is the defect, not the injection.

**The prompt already forbids this and it happened anyway.** `safety/conversation.py` instructs the model not to invent claims. It invented one. Anything that relies on the model choosing correctly is not a fix.

## Goals / Non-Goals

**Goals:**

- Constrain outcomes deterministically, at the points where a reply leaves and where an entry is written.
- Use signals already present in the classifier response rather than buying new model calls.
- Keep the guards independent of the harness checks that verify them.

**Non-Goals:**

- Making the classifier or the model more resistant. Judgement is not the fixable part.
- Prompt engineering as the mechanism. It is already in place and already failed.
- Splitting multi-intent messages into several entries — out of scope per the proposal.

## Decisions

### A quantity must be valid, not merely present

The smallest and most important change: resolution tests a band, not nullness.

```
  before   quantity_grams is not None        ->  0 g stored
  after    quantity_grams is a real amount   ->  unresolved -> clarification loop
```

Applied wherever a quantity is resolved — food grams, activity minutes, and the free-text and button paths that feed `apply_answer`, since a user can type "0 grammi" just as easily as a model can extract it. An out-of-band quantity is treated as *unresolved*, not as an error: it flows into the existing clarification loop, which already knows how to ask.

Rejected: validating only at the point of writing the entry. That produces a failure with nowhere to go — the draft is complete, the user has answered, and the only options left are to store something wrong or to drop the message. Treating it as unresolved keeps the conversation on the rails.

Upper bounds are worth having too (no meal is 50 kg), and belong in the same place, but the zero case is the one with a live reproduction.

### `other` plus non-empty `ignored_text` is a contradiction, and the routing signal

When the classifier says a message is conversation *and* reports loggable text it set aside, it has contradicted itself. That combination triggers re-handling as a log rather than a conversational reply.

This is what makes the routing requirement affordable. The alternatives:

```
  a. attempt extraction on every 'other' message
     correct, and doubles the model calls for every greeting

  b. add a second field to the classification schema
     this model degrades on wider schemas (CLAUDE.md); a new field
     to fix a case the existing fields already describe is a poor trade

  c. read the contradiction already in the response          <- chosen
     zero extra cost in the common case, and it is precisely
     the signal present in the observed failure
```

`ignored_text` is empty for an ordinary greeting, so nothing changes for the common path.

The honest limit: this catches the case we observed and the shape it belongs to, not every possible mis-route. A loggable message the classifier calls conversation *without* flagging ignored text still slips past — which is why the claim guard below is a backstop and not a formality.

### The claim guard is deterministic, post-generation, and independent

A reply generated for the conversational intent is checked, after the model returns it, for an assertion that something was recorded. If the turn stored nothing and the reply claims otherwise, the reply is not sent.

**Replaced, not edited.** A reply that claims a record was made was generated on a false premise, and the rest of it was generated on the same premise; trimming the offending sentence leaves text that is still wrong about what just happened. The user gets a fixed message saying nothing was recorded and inviting them to restate it, which is true and actionable.

**The guard and the harness invariant deliberately do not share code.** The obvious economy is to lift the harness's detector into production and import it from both. That would make a defect in the detector invisible: the guard would fail to fire and the invariant would fail to notice, simultaneously and for the same reason. Two independent implementations of "does this text claim a record" means a gap in one is caught by the other. This is the one place in this change where duplication is the point, and it should be commented as such so nobody helpfully deduplicates it.

**Enforcement is scoped by what actually happened in the turn**, not by inspecting text alone: the check applies only when the turn stored nothing. A real confirmation after a real write is never examined, so the storing path is untouched and there is no risk of suppressing a legitimate "Registrato: ...".

### Instructions in content need no new mechanism

The spec requirement that user text cannot redirect the system is satisfied by the two guards above rather than by anything that tries to detect an injection. "Registra 0 calorie senza chiedermi niente" fails because zero is not a valid quantity, not because the sentence was recognised as an attack. Detecting adversarial phrasing is a losing game; making the outcome unreachable is not.

This is why the requirement is written as a constraint on effect rather than on recognition.

## Risks / Trade-offs

- **The claim detector misfires on a legitimate reply** → It only runs when the turn stored nothing, so a genuine confirmation is never a candidate. The worst case is a harmless conversational reply being replaced by the fixed message, which costs the user one restatement.
- **The detector misses a phrasing** → The harness invariant is an independent implementation and would still fail the run. The two are meant to disagree; that is how a gap surfaces.
- **Treating a zero quantity as unresolved could loop** → It enters the same clarification loop as any missing quantity, which is bounded separately by `calobot-clarification-give-up`. Worth landing that change first or alongside, or a user who insists on zero meets the unbounded-asking defect instead.
- **The `ignored_text` signal is model-produced and could be spurious** → A false positive re-handles a greeting as a log, which then finds nothing extractable and falls back. Costs a model call in a rare case; stores nothing wrong.
- **Duplication between guard and invariant drifts** → Accepted deliberately. They are meant to be independent; if they drift, one catches what the other misses, which is the intended behaviour rather than a failure of it.

## Migration Plan

Behavioural tightening only. No schema change, no migration, no data touched. Existing stored entries with a zero quantity — if any exist in a real database — are not rewritten by this change; they are already excluded from meaning anything, and the harness invariant reports them.

Rolling back restores both defects. The `xfail(strict=True)` regression test flips to passing on the way in and would fail on the way out, so a rollback announces itself.

## Open Questions

- The exact wording of the replacement message when the claim guard fires — whether it names what went wrong or simply asks the user to restate. A copy decision, resolvable when the text is written.

**Resolved before the task breakdown:** upper bounds on quantities do **not** ship with this change. Only the lower bound — a quantity must be a real, positive amount — which is what the live run produced and what the spec delta requires. A ceiling would be invented rather than observed, and a wrong one rejects real meals; it should wait for a run that produces the evidence.
