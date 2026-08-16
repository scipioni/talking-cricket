## Why

Logging a meal by typing is already the cheapest interaction a food tracker can offer, but a photo is cheaper still — and the model Calobot already runs, `qwen3-vl`, can see. Three distinct openings follow from that, and they are not equally valuable:

A **nutrition label** photo yields kilocalories per 100 grams as a printed fact, requiring no matching, no database and no estimation; it is the most accurate input the system can receive and the cheapest to build. A **dish** photo removes the hardest part of typing a meal — naming several foods at once. A **barcode** identifies a packaged product exactly, but needs the most infrastructure for the least incremental gain over a label photo.

This change adds all three, in that order of confidence, on top of the seams `calobot-v1` deliberately left: an extraction interface that already accepts `text | image`, a resolution cache keyed on normalized descriptions with provenance, and a clarification loop that already knows how to ask for a portion.

**Depends on `calobot-v1`**, which must be implemented and archived first.

## What Changes

- **Photo intake**: inbound Telegram photos are downloaded, normalized to a bounded size and passed to the extraction layer as image content. This replaces v1's placeholder reply stating that photo recognition is unavailable.
- **Photo intent classification**: a photo is classified as a nutrition label, a barcode, a dish, or unrecognizable, so that each takes its own path. A caption, when present, informs the classification and the extraction.
- **Nutrition label reading**: the system reads energy per 100 grams, and the product name where legible, directly from the label and writes it into the resolution cache with a new provenance value. This bypasses the food composition table entirely for packaged products.
- **Dish recognition**: the system identifies the foods visible in a photo and creates one draft per food, then uses the existing clarification loop to obtain portions. The system does **not** estimate portion sizes from image geometry.
- **Barcode scanning**: barcodes are decoded from the image by a dedicated decoder, never read as digits by the language model, and looked up against OpenFoodFacts at runtime. Attribution is presented as required by ODbL.
- **Portion clarification for photos**: unchanged in mechanism, but every photo-derived entry must pass through it, because no photo establishes quantity.
- **Confirmation and correction**: photo-derived entries are confirmed and corrected through exactly the same controls as typed entries; a misidentified food is corrected rather than re-photographed.
- **BREAKING** for `message-ingestion`: the Input modality contract requirement changes from "reply that photo recognition is unavailable" to full image handling.

Explicitly **out of scope**: estimating grams from image geometry or reference objects; multi-photo sessions; video; recognizing a restaurant menu; storing photos after processing.

## Capabilities

### New Capabilities

- `photo-input`: photo intake and normalization, photo intent classification, nutrition label reading, dish recognition, barcode decoding and product lookup, the retention rule for received images, and the failure behaviour when a photo cannot be interpreted.

### Modified Capabilities

- `message-ingestion`: the Input modality contract requirement is replaced — images are processed rather than refused, and photo handling shares the classification, draft, clarification and language model contracts already defined there.

## Impact

- **New dependencies**: a barcode decoding library backed by a system-level library (`zbar`), which must be installed in the runtime image rather than resolved by `uv` alone; an image handling library for downscaling; an HTTP client for OpenFoodFacts.
- **Modified components**: the Telegram handler layer gains a photo handler; the extraction layer gains image-carrying calls; the resolution cache gains `etichetta` and `off` provenance values; the food entry confirmation path is unchanged.
- **Licensing**: OpenFoodFacts data is ODbL. It is used at runtime and never bundled, so the obligation is satisfied by visible attribution; this is why `calobot-v1` deliberately kept OpenFoodFacts out of the bundled seed data.
- **Cost and latency**: image inference is substantially more expensive per call than text on the same model. The self-hosted endpoint has no token limits, but per-message latency will rise and the typing indicator becomes load-bearing.
- **Privacy**: photos of food are personal data and may incidentally capture people or surroundings. Images are processed and discarded, never persisted, and this must be stated to the user.
- **Deployment**: the runtime image grows by the barcode and imaging system libraries.
