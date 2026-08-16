## 1. Photo intake

- [ ] 1.1 Add a Telegram photo handler that downloads the largest available photo size and its caption
- [ ] 1.2 Downscale images to a bounded resolution before inference, with the resolution configurable and separately configurable for labels
- [ ] 1.3 Reject non-image and unprocessable files with a plain message and no stored data
- [ ] 1.4 Ensure the typing indicator covers the whole download, inference and resolution sequence
- [ ] 1.5 Remove v1's placeholder reply stating that photo recognition is unavailable
- [ ] 1.6 Guarantee images are discarded after interpretation, including on the error paths, and add a test asserting nothing is written to disk

## 2. Photo classification

- [ ] 2.1 Implement the photo classifier returning label, barcode, dish or unrecognizable, accepting the caption as additional context
- [ ] 2.2 Run the barcode decoder first and treat a checksum-valid decode as definitive, falling through to classification on failure
- [ ] 2.3 Prefer the label path when a photo yields both a decodable barcode and a legible nutrition label
- [ ] 2.4 Handle the unrecognizable case by suggesting a typed entry and storing nothing

## 3. Nutrition label reading

- [ ] 3.1 Implement label extraction returning energy per 100 g, the product name where legible, and the unit read
- [ ] 3.2 Convert kilojoules to kilocalories when energy is stated only in kilojoules
- [ ] 3.3 Derive energy per 100 g from a per-portion label when the portion weight is legible, and ask the user when it is not
- [ ] 3.4 Apply plausibility bounds to the extracted energy density and reject impossible values
- [ ] 3.5 Write the result to the resolution cache with `etichetta` provenance keyed on the normalized product name
- [ ] 3.6 Handle illegible labels by asking for a clearer photo and storing nothing
- [ ] 3.7 Add tests over a set of real Italian label photographs, including per-portion, kilojoule-only and blurred cases

## 4. Barcode scanning

- [ ] 4.1 Add the `zbar` system library to the runtime image stage and its Python binding to the project dependencies
- [ ] 4.2 Implement barcode decoding that returns only checksum-valid codes and never infers digits from the model
- [ ] 4.3 Implement the OpenFoodFacts lookup client with a bounded timeout, returning product name and energy per 100 g
- [ ] 4.4 Write results to the resolution cache with `off` provenance, and show the product name in the confirmation
- [ ] 4.5 Handle product-not-found by suggesting the label path, and service-unavailable by saying so and storing nothing
- [ ] 4.6 Present ODbL attribution wherever a value obtained from the lookup service is shown
- [ ] 4.7 Add tests for a valid decode, an undecodable image, an unknown product and an unreachable service

## 5. Dish recognition

- [ ] 5.1 Implement dish extraction returning a list of identified foods with no quantities
- [ ] 5.2 Create one draft per identified food and resolve them sequentially through the existing clarification loop
- [ ] 5.3 Abandon the remaining queued drafts with an explicit notice when the user abandons or cancels one
- [ ] 5.4 Assert in code and in tests that no entry from a dish photo is stored before a quantity is supplied
- [ ] 5.5 Verify a misidentified food is correctable through the existing correction controls without another photo

## 6. Provenance and trust ordering

- [ ] 6.1 Add `etichetta` and `off` to the provenance values of the resolution cache
- [ ] 6.2 Implement the trust ordering `etichetta` > `off` > `tabella` > `llm`, allowing a higher-trust value to overwrite a lower-trust one for the same key
- [ ] 6.3 Show the source of the value in confirmations for label- and lookup-derived entries
- [ ] 6.4 Add a test that a typed mention of a previously photographed product resolves from the cache with label provenance

## 7. Wording and privacy

- [ ] 7.1 Tell the user on their first photo that photos are processed and not kept
- [ ] 7.2 Word the first photo interaction so the portion question is expected rather than a surprise
- [ ] 7.3 Update the README and any onboarding copy to describe what photos can and cannot do

## 8. End-to-end verification

- [ ] 8.1 Exercise all three paths against the real endpoint with real photographs: label, barcode, dish with several foods
- [ ] 8.2 Measure per-photo latency at the chosen downscale resolution and confirm labels remain legible at it
- [ ] 8.3 Verify photo-derived entries appear in reports identically to typed entries
- [ ] 8.4 Verify that rolling back to the previous image leaves all data written by this change valid
