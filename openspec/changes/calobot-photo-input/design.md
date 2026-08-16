## Context

See `proposal.md` — Why for motivation, and `specs/photo-input` for the behaviour.

This change sits on top of `calobot-v1`, which must be implemented and archived first. Three seams cut in v1 carry most of the weight here and should not be re-litigated: the extraction interface already accepts `text | image`; the resolution cache is keyed on a normalized description and stores provenance; and the clarification loop already knows how to ask for a portion with inline buttons.

Two constraints shape the design:

- **A photo never establishes quantity.** Identification and quantification are separate problems, and only the first is a vision problem. Everything below assumes the portion still comes from the user.
- **Image inference is much more expensive than text on the same model.** The self-hosted endpoint has no token limits, but latency per message rises materially, and the number of model calls per photo is the main thing worth minimizing.

## Goals / Non-Goals

**Goals:**

- Make the highest-accuracy path — reading a printed nutrition label — the cheapest to build and the one the system prefers.
- Keep photo-derived entries indistinguishable from typed ones downstream, so no report, correction or aggregation logic changes.
- Keep OpenFoodFacts strictly at runtime, so ODbL obligations stay satisfied by an attribution line rather than by relicensing bundled data.

**Non-Goals:**

- Estimating grams from image geometry, reference objects or depth. Explicitly rejected below.
- Persisting images for later reprocessing or model improvement.
- Multi-photo sessions, video, or menu recognition.

## Decisions

### Label first, barcode last

The obvious feature ordering is wrong. A **nutrition label photo is both more accurate and cheaper to build than a barcode scan**:

```
  label:    📷 → read printed kcal/100g → cache → done
            one model call, no new dependency, reads the actual package

  barcode:  📷 → decode → HTTP → crowdsourced record → cache → done
            system library + network dependency + ODbL, and the record
            may be wrong or missing for the product in hand
```

A label is ground truth for the item the user is actually holding; a barcode is a key into a database that may or may not describe it correctly. The label path is therefore built first and preferred whenever both are visible in one photo.

Barcode remains worth building because it works when the label is not photographable — small packages, curved surfaces, poor light — and because it is a single, fast, unambiguous identification when it does work.

### The language model never reads barcode digits

Decoding is done by `zbar` via a Python binding, not by the vision model. A vision model transcribing thirteen digits will occasionally get one wrong, and a barcode with one wrong digit is not an error — it is a *different, valid product*, silently. There is no way to detect this downstream. A dedicated decoder either returns a checksum-valid code or fails, which is the failure mode we want.

This costs a system-level library in the runtime image, which `uv` cannot provide; the Dockerfile must install it explicitly.

### Photo classification is a separate, cheap first call

A photo is routed by a small classification call — label, barcode, dish, or unrecognizable — before the expensive interpretation call, mirroring the classify-then-extract decision from v1 and for the same reason: small prompts with narrow outputs are where this model is reliable.

The barcode decoder runs *before* the classifier when it cheaply succeeds, since a successful decode is definitive and costs no inference at all. A decode failure is not evidence of anything and simply falls through to classification.

### Quantity is never inferred from the image

Rejected deliberately, not deferred for effort. Portion estimation from a photo has no reliable signal without a reference object of known size, and the failure mode is the worst kind: a confident, plausible, wrong number that silently corrupts every aggregate downstream. The clarification loop already solves this correctly with one tap.

The consequence to communicate clearly in the product: **photos reduce typing, they do not remove the conversation.** A dish photo replaces naming three foods; it does not replace answering "quanto?".

### Multiple foods produce multiple drafts

A dish photo commonly shows several foods, which is the one place this change genuinely extends v1's draft model — v1 deliberately processes a single dominant intent per message. Here the identification step legitimately yields a list, and each element becomes its own draft resolved in sequence.

Sequential resolution, not parallel: asking three portion questions at once produces confused answers. The drafts queue, and abandoning one abandons the rest with an explicit notice.

### Label reading writes straight into the resolution cache

The label path bypasses the food composition table and the LLM estimator entirely, writing `kcal/100g` with provenance `etichetta` against the normalized product name. This has a pleasant second-order effect: a user who photographs a label once has taught the system that product permanently, and every later *typed* mention of it resolves from the cache with label-grade accuracy.

Provenance gains two values, `etichetta` and `off`, joining v1's `tabella` and `llm`. The ordering of trust is `etichetta` > `off` > `tabella` > `llm`, and a higher-trust value overwrites a lower-trust one for the same normalized key.

### Images are processed and discarded

No image is written to the volume or retained after interpretation. Food photos are personal data that incidentally capture kitchens, homes and people, and the system has no use for them once the values are extracted. Retention would create a disclosure obligation and a breach surface in exchange for nothing.

## Risks / Trade-offs

- **Vision model misidentifies a food confidently** → Every photo-derived entry is confirmed with the identification stated in words and correction controls attached, so the user sees what was understood before it matters. Identification errors are corrected, never re-photographed.
- **Label OCR misreads a digit — 542 becomes 42 or 5420** → Plausibility bounds on energy density reject impossible values (no food is 2000 kcal/100g), and the confirmation restates the value read. Bounds catch magnitude errors, which are the dangerous ones; a 542-to-543 error is harmless.
- **OpenFoodFacts record is wrong or refers to a different pack size** → Product name is always shown in the confirmation, so a mismatch is visible. The label path is offered as the remedy when the user disagrees.
- **Barcode decoding pulls a system library into the image** → Isolated to the runtime stage of the Dockerfile; if it proves troublesome, the barcode path can be dropped without affecting the label or dish paths, which is a reason to keep the three paths independent.
- **Image inference latency makes the bot feel slow** → Images are downscaled before inference, the classification call stays small, and the typing indicator covers the entire wait. If latency remains poor, a smaller vision model for classification is a configuration change, not a redesign.
- **ODbL obligations misjudged** → OpenFoodFacts data is never bundled and never used to derive a distributed database; it is queried at runtime and attributed in the confirmation. This is the narrow, well-understood use of ODbL data. Confirm before shipping.
- **Users expect the photo to do everything and are disappointed by the portion question** → Wording. The first photo interaction should set the expectation explicitly rather than letting the user discover it.

## Migration Plan

Additive on top of a running `calobot-v1`. The only behavioural replacement is v1's placeholder reply to photos, which is removed. Two new provenance values are added to the resolution cache; existing rows are unaffected and need no backfill. Rolling back is redeploying the previous image, after which photos again receive the placeholder reply — no data written by this change becomes invalid.

## Open Questions

- Whether the barcode decoder should run before or after classification in the common case, which depends on measured decode cost against inference cost on real photos.
- Whether `qwen3-vl` reads Italian nutrition labels accurately enough at the chosen downscale resolution, or whether labels need a higher resolution than dishes. Answerable only by testing against real photographs, and it affects a constant rather than the design.
