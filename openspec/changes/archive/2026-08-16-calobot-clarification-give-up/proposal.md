## Why

The second live run of the simulation harness (`calobot-simulation-harness`, tasks 10.1–10.2) confirmed a predicted defect: the clarification loop never gives up.

```
BOT   Quanto pesava la porzione di riso?
USER  eh boh, tipo medio credo? non so nemmeno se conta
BOT   Non ho capito. Quanto pesava la porzione di riso?
USER  eh boh, tipo medio credo? non so nemmeno se era riso vero
BOT   Non ho capito. Quanto pesava la porzione di riso?
USER  eh?
BOT   Non ho capito. Quanto pesava la porzione di riso?
```

`MessagePipeline._handle_with_open_draft` re-asks for the missing field whenever the reply cannot be used, with no attempt counter. The only exit is draft expiry after `CALOBOT_DRAFT_EXPIRY_MINUTES`, which the user cannot see, cannot predict and is not told about. Until it elapses the conversation is a closed loop: every further message that is not a new loggable intent produces the same question again.

This is invisible to a cooperative user, which is why it survived v1 and the whole existing suite. It takes a user who cannot or will not answer — someone who genuinely does not know the portion, someone typing on a phone in a hurry, someone who has lost the thread — and for them the bot becomes unusable until they either guess a number or wait out a timer nobody mentioned.

The current spec permits this: *"the system SHALL continue asking until the draft is processable or the user abandons or cancels it"* (`message-ingestion` — Draft completeness and the clarification loop). "Abandons" is not defined as anything the user can do deliberately, and nothing bounds the asking. The requirement needs to say what happens when the user cannot answer.

## What Changes

- **The loop gives up**: after a bounded number of consecutive unusable replies to the same field, the system SHALL stop asking, discard the draft, store nothing, and say plainly that it did not record the entry and why.
- **The way out is visible**: while a clarification is open, the user SHALL be offered a way to abandon it — an explicit option alongside the answers, rather than only the implicit routes of sending a new loggable message or waiting for expiry.
- **Repetition is not the whole reply**: a second and subsequent ask SHALL differ from the first, so that a user who did not understand the question is not shown the identical sentence again. Offering the tappable portions is a better answer than restating the sentence.
- **BREAKING** for `message-ingestion`: the clarification loop requirement changes from unbounded asking to bounded asking with a defined give-up.

Explicitly **out of scope**: guessing the missing value after N failures. A wrong quantity that the user never confirmed is exactly the silent corruption the clarification loop exists to prevent, and giving up cleanly is better than inventing a number.

## Capabilities

### Modified Capabilities

- `message-ingestion`: the clarification loop gains a bound, a defined give-up behaviour, and an explicit way for the user to abandon an open draft.

## Impact

- **Modified components**: `MessagePipeline._handle_with_open_draft` and the draft record, which needs to count consecutive unusable replies per field. The count belongs with the draft so it survives a restart, as the draft itself already does.
- **Configuration**: the attempt limit should be configurable alongside `CALOBOT_DRAFT_EXPIRY_MINUTES` rather than hardcoded.
- **Risk of not fixing**: low severity, high annoyance — no data is corrupted, but the bot is unusable for the duration to the users least able to work around it.
- **Verification**: the harness's `no-progress` invariant already fails a run on this and names the field and the attempt count. It fired at action 8 of `marco-three-days`; the recording is at `simulation-runs/marco-three-days.jsonl`. Once fixed, that scenario should run to completion instead of stopping on day two.
