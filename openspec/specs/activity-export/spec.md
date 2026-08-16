# activity-export Specification

## Purpose

Extracts and exports complete, chronologically ordered session activity logs in a structured JSON schema, enabling offline analysis by external tools or AI agents.

## Requirements

### Requirement: Unified session activity schema

The system SHALL define a structured JSON schema representing the chronological timeline of a chat session, which includes user messages (including media/images and text), bot replies (including text and reply inline markups), and all underlying LLM calls (step names, models, prompts, inputs, outputs, errors, and validation retries) associated with that session.

#### Scenario: Validate schema fields
- **WHEN** a session log is generated for export
- **THEN** it must conform to the unified activity schema, containing a chronological timeline array of messages and LLM transactions

### Requirement: Session history export API

The system SHALL expose an HTTP REST endpoint (`/api/export/{chat_id}`) that retrieves the complete history of a specific chat session in the unified JSON format.

#### Scenario: Exporting a valid chat session
- **WHEN** an authenticated client makes a GET request to `/api/export/4829104` for a chat ID with existing history
- **THEN** the system returns a status code of 200 with the full structured JSON payload

#### Scenario: Exporting an empty or invalid chat session
- **WHEN** a client makes a GET request to `/api/export/9999999` for a chat ID that has no recorded events
- **THEN** the system returns a status code of 404 with an appropriate error payload
