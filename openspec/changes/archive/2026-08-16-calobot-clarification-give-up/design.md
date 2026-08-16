## Context

See `proposal.md` — Why for the finding, and `specs/message-ingestion` for the behaviour.

Four facts about the current code shape the approach.

**The re-ask already offers the buttons.** `MessagePipeline._handle_with_open_draft` returns `OutgoingMessage(text=f"Non ho capito. {clarification.question_text}", buttons=clarification.options)`. So the spec's "present the tappable options again" is already satisfied; what is missing is that attempts two, three and four are *identical*, and that nothing counts them.

**The draft payload is JSON.** `PendingDraft.payload` is a `JSON` column already holding `{"items": [...], "current_index": n}`. A per-draft attempt counter fits inside it with no schema change and therefore no Alembic revision — and it inherits the persistence the draft already has, so a count survives a restart exactly as the draft does.

**A clarification message is assembled in more than one place.** The food and activity advance paths and the not-understood path each build their own `OutgoingMessage` from a `ClarificationNeeded`. Three behaviours in this change — count the attempt, vary the wording, offer the way out — all attach to that assembly.

**There is now a second route into this loop.** Since `calobot-false-confirmation`, a quantity that resolves to zero is treated as unresolved, which sends it here. A user who insists on zero meets this defect rather than the old one. That raises the priority but changes nothing about the fix.

## Goals / Non-Goals

**Goals:**

- Bound the asking and end it in a state the user can understand and act on.
- Make the way out visible where the user is already looking, which is at the buttons.
- Keep the fix inside the existing draft lifecycle, with no schema change.

**Non-Goals:**

- Guessing the missing value after N failures. Out of scope per the proposal, and it is the exact corruption the loop exists to prevent.
- Changing what counts as an acceptable answer. This change bounds the asking; it does not make parsing more generous.
- Making the expiry timer visible. Expiry stays what it is — a backstop nobody should reach now that there is a real exit.

## Decisions

### The counter lives in the draft payload

```
  payload  {"items": [...], "current_index": 0, "attempts": 2}
```

Rejected: a new column on `pending_drafts`. It would need an Alembic revision for a value that is ephemeral per-draft state, of interest to nobody after the draft closes, and never queried across rows. The JSON payload is where the rest of that state already lives.

A draft written before this change has no `attempts` key; a missing key reads as zero, so drafts in flight across a deploy behave as if they had just started counting. No backfill.

### One place assembles a clarification message

A single helper turns a `ClarificationNeeded` plus the current attempt count into the outgoing message. Counting, wording and the way out then live together, and the three call sites become one call each.

The alternative — patching each site — was rejected not for effort but because it is how the three behaviours drift apart. The bug being fixed exists partly because "ask again" was written twice.

### Varied wording is a rotation, not a model call

The second ask and the third differ by selecting from a small fixed list of phrasings, indexed by the attempt count.

Rejected: asking the model to rephrase. That spends a call, and latency, at the exact moment the user is already stuck and irritated, to produce a sentence that can be written in advance. It would also make the wording non-deterministic, so a scenario could not assert on it.

The rotation is not decoration. A user who did not understand the question is shown a differently-worded one, which is the only chance the second attempt has of doing better than the first.

### The way out is a button, not a command

The abandon option is appended to the clarification's tappable options.

`/annulla` already exists, but a command the user has to know about is not a visible way out — the proposal's requirement is that it be *offered*. The user is already looking at a row of buttons; the exit belongs there.

It is matched as an exact sentinel string before the answer is handed to `apply_answer`, so it cannot be confused with a portion. The label is deliberately not a plausible answer to any clarification.

### Give-up discards, and says which entry it dropped

On reaching the limit the draft is discarded through the existing path, nothing is stored, and the reply names what was not recorded and invites the user to send it again. Naming it matters: after four exchanges about a portion, "non ho registrato niente" without saying *what* leaves the user unsure whether an earlier entry also vanished.

### The production bound must be tighter than the harness bound

The simulation harness fails a run when the draft state does not change for more than `progress_limit` consecutive actions. If the bot gives up at N attempts and the harness fires at more than M, then **N must be less than or equal to M**, or correct give-up behaviour trips the harness and every run reports a false finding.

The harness currently uses 3. The production limit should be set with that relationship in mind and the harness's default revisited alongside it, rather than either being chosen alone. This is the one cross-repository constraint in the change and the easiest thing here to get wrong.

## Risks / Trade-offs

- **A user who would have answered on attempt N+1 loses their draft** → The give-up message names the entry and invites them to send it again, which costs one message. The limit is configurable, so it can be loosened from a real run rather than argued about in advance.
- **The abandon label is chosen by the model as a portion answer** → It is matched as an exact literal and worded so as not to be a plausible answer. The check runs before parsing, so even a coincidence resolves to abandonment rather than a quantity.
- **The counter and the harness's notion of "advancing" drift apart** → They are independent implementations of the same idea, deliberately, for the same reason as the claim detectors. If they disagree, the harness reports a stall the bot thought it had ended — which is a finding, not a nuisance.
- **The wording rotation runs out on a long stall** → It cannot: the limit is reached before the rotation is exhausted, by construction. Worth an assertion rather than a comment.
- **Drafts in flight during a deploy** → A missing `attempts` key reads as zero. The worst case is a user mid-stall getting the full allowance again, once.

## Migration Plan

No schema change and no data migration: the counter is a key in an existing JSON column, and its absence is a valid state meaning zero.

One new configuration value with a default, so an existing deployment needs no environment change.

Rolling back restores the unbounded loop. Drafts carrying an `attempts` key are still valid to the previous code, which ignores it.

## Open Questions

- The attempt limit's default value, and whether the harness's `progress_limit` moves with it. Constrained by the relationship above rather than free, and best set from a live run where a real persona gives real unusable answers.
- The wording of the rotation and of the give-up message. Copy, resolvable when written.
