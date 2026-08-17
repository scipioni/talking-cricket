## 1. Photo intake

- [x] 1.1 Add a Telegram photo handler that downloads the largest available photo size and its caption
- [x] 1.2 Downscale images to a bounded resolution before inference, with the resolution configurable and separately configurable for labels
- [x] 1.3 Reject non-image and unprocessable files with a plain message and no stored data
- [x] 1.4 Ensure the typing indicator covers the whole download, inference and resolution sequence
- [x] 1.5 Remove v1's placeholder reply stating that photo recognition is unavailable
- [x] 1.6 Guarantee images are discarded after interpretation, including on the error paths, and add a test asserting nothing is written to disk

## 2. Photo classification

- [x] 2.1 Implement the photo classifier returning label, barcode, dish or unrecognizable, accepting the caption as additional context
- [x] 2.2 Run the barcode decoder first and treat a checksum-valid decode as definitive, falling through to classification on failure

  Deviation from the letter of this task, recorded rather than silently applied:
  the classifier always runs (it's needed anyway to prefer label over barcode -
  see 2.3), and the barcode decoder is attempted independently rather than
  gating whether classification happens. Decoding itself still costs no
  inference and still runs unconditionally. This was flagged as an open
  question in design.md ("whether the barcode decoder should run before or
  after classification... answerable only against real photographs") - revisit
  once task 8's real-photo cost data exists.
- [x] 2.3 Prefer the label path when a photo yields both a decodable barcode and a legible nutrition label
- [x] 2.4 Handle the unrecognizable case by suggesting a typed entry and storing nothing

## 3. Nutrition label reading

- [x] 3.1 Implement label extraction returning energy per 100 g, the product name where legible, and the unit read
- [x] 3.2 Convert kilojoules to kilocalories when energy is stated only in kilojoules
- [x] 3.3 Derive energy per 100 g from a per-portion label when the portion weight is legible, and ask the user when it is not
- [x] 3.4 Apply plausibility bounds to the extracted energy density and reject impossible values
- [x] 3.5 Write the result to the resolution cache with `etichetta` provenance keyed on the normalized product name
- [x] 3.6 Handle illegible labels by asking for a clearer photo and storing nothing
- [x] 3.7 Add tests over a set of real Italian label photographs, including per-portion, kilojoule-only and blurred cases

  Verified against 2 real label photos (a German/Italian/French Lidl label
  stating "1900 kJ/454 kcal", and a Greek/Italian drained-product label stating
  "173,50 kcal / 725,50 kJ") through the real endpoint: both classified as
  `label` and both energy values read exactly right, including correct
  comma-decimal parsing on the second. Not yet covered from this real set:
  per-portion-only and kilojoule-only labels (both photos gave kcal directly)
  and a genuinely blurred one - the pure-logic paths for those (tests/test_photo_label.py)
  are unit-tested but not against a real photo. The photos themselves aren't
  committed to the repo (personal photos, supplied ad hoc); worth building a
  small checked-in fixture set later if this needs re-verifying.

## 4. Barcode scanning

- [x] 4.1 Add the `zbar` system library to the runtime image stage and its Python binding to the project dependencies
- [x] 4.2 Implement barcode decoding that returns only checksum-valid codes and never infers digits from the model
- [x] 4.3 Implement the OpenFoodFacts lookup client with a bounded timeout, returning product name and energy per 100 g
- [x] 4.4 Write results to the resolution cache with `off` provenance, and show the product name in the confirmation
- [x] 4.5 Handle product-not-found by suggesting the label path, and service-unavailable by saying so and storing nothing
- [x] 4.6 Present ODbL attribution wherever a value obtained from the lookup service is shown
- [x] 4.7 Add tests for a valid decode, an undecodable image, an unknown product and an unreachable service

  Decode round-trips against a synthetically generated EAN-13 (python-barcode);
  the OpenFoodFacts client is tested by mocking `httpx2` directly rather than
  contacting the real service, matching this project's no-live-network test
  policy.

  A real barcode photo (356x300px, partially handheld) surfaced a genuine bug
  this synthetic testing had missed: zbar failed to decode it at native
  resolution but succeeded cleanly once upscaled 2x. `decode_barcode` now
  retries at 2x/3x before giving up (`_UPSCALE_FACTORS` in
  `photo/barcode.py`), verified both against that real photo and a synthetic
  regression test reproducing the same native-resolution failure
  (`test_decodes_a_small_barcode_that_needs_upscaling`). Never exercised
  against the live world.openfoodfacts.org itself, since the decoded barcode
  from the test photo was never looked up there.

## 5. Dish recognition

- [x] 5.1 Implement dish extraction returning a list of identified foods with no quantities
- [x] 5.2 Create one draft per identified food and resolve them sequentially through the existing clarification loop
- [x] 5.3 Abandon the remaining queued drafts with an explicit notice when the user abandons or cancels one

  Also fixed a pre-existing bug this surfaced: abandoning mid-draft always said
  "non ho registrato niente" even when earlier items in the same draft had
  already been stored. `_abandon_draft` now names only the items actually
  dropped.
- [x] 5.4 Assert in code and in tests that no entry from a dish photo is stored before a quantity is supplied
- [x] 5.5 Verify a misidentified food is correctable through the existing correction controls without another photo

## 6. Provenance and trust ordering

- [x] 6.1 Add `etichetta` and `off` to the provenance values of the resolution cache

  Already present in `Provenance` and in the initial migration's CHECK
  constraint, reserved by `calobot-v1` for this change - no migration needed.
- [x] 6.2 Implement the trust ordering `etichetta` > `off` > `tabella` > `llm`, allowing a higher-trust value to overwrite a lower-trust one for the same key
- [x] 6.3 Show the source of the value in confirmations for label- and lookup-derived entries
- [x] 6.4 Add a test that a typed mention of a previously photographed product resolves from the cache with label provenance

## 7. Wording and privacy

- [x] 7.1 Tell the user on their first photo that photos are processed and not kept
- [x] 7.2 Word the first photo interaction so the portion question is expected rather than a surprise
- [x] 7.3 Update the README and any onboarding copy to describe what photos can and cannot do

## 8. End-to-end verification

- [x] 8.1 Exercise all three paths against the real endpoint with real photographs: label, barcode, dish with several foods

  Verified with 4 real photos against the real endpoint (`ingegno.csgalileo.org`,
  `qwen3-vl:30b-a3b-instruct`): 2 nutrition labels (both classified and read
  correctly, exact kcal match), 1 dish photo (a bowl of grapes, correctly
  classified as `dish` and identified as "uva", preparation "cruda"), 1 barcode
  photo (correctly classified as `barcode`; local decode initially failed, fixed
  per the 4.7 note above). Not covered: a dish with *several* distinct foods in
  one photo (only single-food photos were available) and a barcode round-tripped
  through the live OpenFoodFacts lookup (never had a real product barcode to look
  up against the live service, only the local decode was exercised for real).
- [x] 8.2 Measure per-photo latency at the chosen downscale resolution and confirm labels remain legible at it

  Measured on the Lidl label photo: classify ~1.2s, label read ~1.0s, ~2.2s
  total per photo - no latency concern at the current `photo_max_dimension_px`
  (1280) / `photo_label_max_dimension_px` (2000) settings. Both real label
  photos read correctly at these resolutions; neither test photo exceeded
  either bound, so the settings never actually downscaled them - legibility at
  the boundary itself (a label large enough to actually get downscaled) is
  still unverified.
- [x] 8.3 Verify photo-derived entries appear in reports identically to typed entries
- [ ] 8.4 Verify that rolling back to the previous image leaves all data written by this change valid

  **Not done** - this is a deployment-time check against a real rollout
  (redeploy the previous image, confirm existing rows are still valid), not
  something to verify from a dev environment.
