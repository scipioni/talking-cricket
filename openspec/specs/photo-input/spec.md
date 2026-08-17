# photo-input Specification

## Purpose

Lets a user log by pointing a camera instead of typing, covering the three distinct things a food photo can be: a nutrition label, a barcode, or a plate of food. It defines how each is interpreted, how confidently, and what the system does when a photo cannot be understood.

## Requirements

### Requirement: Photo intake

The system SHALL accept photos sent in chat, download them, and pass them to the extraction layer as image content. Images SHALL be downscaled to a bounded size before inference. When a photo arrives with a caption, the caption SHALL be supplied alongside the image and SHALL inform interpretation.

#### Scenario: Photo received

- **WHEN** a user sends a photo
- **THEN** the system downloads it, shows that it is working, and interprets it

#### Scenario: Photo with a caption

- **WHEN** a user sends a photo with a caption such as "colazione"
- **THEN** the caption is used together with the image when interpreting the photo

#### Scenario: Unsupported or oversized file

- **WHEN** a user sends an image the system cannot process, or a file that is not an image
- **THEN** the system says it cannot read that file and stores nothing

### Requirement: Photo intent classification

The system SHALL classify each photo as one of: a nutrition label, a barcode, a dish, or unrecognizable, and SHALL route it to the corresponding interpretation path. When a photo contains both a barcode and a legible nutrition label, the system SHALL prefer the nutrition label.

#### Scenario: Nutrition label photo

- **WHEN** a user photographs a nutrition table on a package
- **THEN** the photo is classified as a label and read for energy per 100 grams

#### Scenario: Dish photo

- **WHEN** a user photographs a plate of food
- **THEN** the photo is classified as a dish and the visible foods are identified

#### Scenario: Package showing both a barcode and a label

- **WHEN** a photo shows both a readable barcode and a readable nutrition label
- **THEN** the system reads the nutrition label and does not perform a product lookup

#### Scenario: Unrecognizable photo

- **WHEN** a photo contains no food, no label and no barcode
- **THEN** the system says it did not recognize anything, suggests writing the entry instead, and stores nothing

### Requirement: Nutrition label reading

The system SHALL read the energy value per 100 grams from a photographed nutrition label, together with the product name where legible, and SHALL record the resulting energy density with a provenance indicating it came from a label. When the label states energy only per portion, the system SHALL use the stated portion size to derive the value per 100 grams, and SHALL ask the user when the portion size is not stated.

#### Scenario: Label stating energy per 100 grams

- **WHEN** a legible label states kilocalories per 100 grams
- **THEN** the system records that energy density with label provenance and asks how much the user ate

#### Scenario: Label stating energy per portion only

- **WHEN** a label states energy only per portion and the portion weight is legible
- **THEN** the system derives the value per 100 grams from it

#### Scenario: Energy stated only in kilojoules

- **WHEN** a label states energy only in kilojoules
- **THEN** the system converts it to kilocalories

#### Scenario: Label illegible

- **WHEN** the energy value cannot be read with confidence
- **THEN** the system says it could not read the label, asks for a clearer photo or a typed entry, and stores nothing

### Requirement: Dish recognition

The system SHALL identify the distinct foods visible in a dish photo and create one draft per identified food. The system SHALL NOT estimate quantities from the image; every draft created from a dish photo SHALL obtain its quantity through the clarification loop.

#### Scenario: Single food in the photo

- **WHEN** a photo shows one identifiable food
- **THEN** the system names the food, asks for the portion, and stores the entry once the portion is known

#### Scenario: Several foods in the photo

- **WHEN** a photo shows several distinct foods
- **THEN** the system lists what it identified and obtains a portion for each before storing entries

#### Scenario: Quantity never inferred from the image

- **WHEN** a dish photo is interpreted
- **THEN** no entry is stored until the user has supplied or confirmed a quantity

#### Scenario: Identification wrong

- **WHEN** the system names a food the user did not eat
- **THEN** the user can correct the identification through the same correction controls as a typed entry, without sending another photo

### Requirement: Barcode decoding and product lookup

The system SHALL decode barcodes from an image using a dedicated barcode decoder, and SHALL NOT accept barcode digits read by the language model. A decoded barcode SHALL be looked up against the OpenFoodFacts service to obtain the product name and energy per 100 grams, recorded with a provenance indicating the source.

#### Scenario: Barcode decoded and product found

- **WHEN** a barcode is decoded and the product exists in the service
- **THEN** the system names the product, records its energy density, and asks how much the user ate

#### Scenario: Product not found

- **WHEN** a barcode is decoded but no matching product exists
- **THEN** the system says the product is unknown and invites the user to photograph the nutrition label instead

#### Scenario: Barcode not decodable

- **WHEN** the image contains a barcode that cannot be decoded
- **THEN** the system asks for a clearer photo and does not attempt to infer the digits

#### Scenario: Lookup service unavailable

- **WHEN** the product lookup service is unreachable or times out
- **THEN** the system says the lookup is temporarily unavailable, suggests photographing the label, and stores nothing

#### Scenario: Attribution presented

- **WHEN** an entry's energy value was obtained from the product lookup service
- **THEN** the system attributes the data to that service as its licence requires

### Requirement: Photo-derived entries are ordinary entries

An entry created from a photo SHALL be indistinguishable in behaviour from a typed entry: it SHALL be confirmed with the same controls, correctable and deletable in the same ways, and included in reports identically. Its provenance SHALL record how its energy value was obtained.

#### Scenario: Correcting a photo-derived entry

- **WHEN** a user corrects an entry that originated from a photo
- **THEN** the correction behaves exactly as it would for a typed entry

#### Scenario: Provenance shown

- **WHEN** an entry's energy came from a label or a product lookup
- **THEN** the confirmation identifies the source of the value

### Requirement: Images are not retained

The system SHALL discard each received image once it has been interpreted, SHALL NOT store images or their content beyond the extracted values, and SHALL tell the user that photos are not kept.

#### Scenario: Image discarded after interpretation

- **WHEN** a photo has been interpreted, whether successfully or not
- **THEN** no copy of the image remains in the system's storage

#### Scenario: User informed about retention

- **WHEN** a user sends their first photo
- **THEN** the system states that photos are processed and not kept
