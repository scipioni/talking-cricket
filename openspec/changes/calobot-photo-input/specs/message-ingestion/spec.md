## MODIFIED Requirements

### Requirement: Input modality contract

The extraction interface SHALL accept either text or an image as the message content. Image content SHALL be interpreted according to the photo-input capability, and SHALL share the draft lifecycle, clarification loop, language model invocation contract and responsiveness feedback defined in this capability.

#### Scenario: User sends a photo

- **WHEN** a user sends a photo
- **THEN** the system interprets it as defined by the photo-input capability rather than refusing it

#### Scenario: Photo interpretation reuses the clarification loop

- **WHEN** a photo yields a draft that is not processable, such as a food without a quantity
- **THEN** the system asks for the missing information using the same clarification loop as a typed message

#### Scenario: Photo interpretation reuses the model invocation contract

- **WHEN** interpreting a photo requires a language model call whose response fails validation
- **THEN** the same bounded retry and graceful failure behaviour applies as for a typed message
