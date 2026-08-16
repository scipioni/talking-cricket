## Purpose

Intercepts all user messages, bot responses, and raw LLM completions in real time to broadcast them over WebSockets to an interactive monitoring dashboard.

## ADDED Requirements

### Requirement: Real-time event interception

The system SHALL intercept every incoming user message, outbound bot response, and LLM gateway call (including prompts, templates, generated outputs, schemas, and retries) without blocking the user's conversational flow.

#### Scenario: User message interception
- **WHEN** an incoming Telegram message is received by the bot
- **THEN** the system intercepts it and publishes an "incoming_update" event to the local event bus

#### Scenario: Bot response interception
- **WHEN** the bot sends an outgoing Telegram message or updates a keyboard
- **THEN** the system intercepts it and publishes an "outgoing_response" event to the local event bus

#### Scenario: LLM gateway call interception
- **WHEN** the LLM gateway is invoked for structured extraction or classification
- **THEN** the system intercepts the request parameters, prompt templates, and eventual raw/parsed completions and publishes an "llm_transaction" event to the local event bus

### Requirement: Causal session tracing

The system SHALL associate every intercepted event with the corresponding `chat_id` and a unique `session_id` using task-local context propagation, ensuring that downstream LLM calls can be correlated to the specific user message that triggered them.

#### Scenario: Correlating LLM calls to a user message
- **WHEN** multiple concurrent users are interacting with the bot
- **THEN** the system propagates `chat_id` using context variables and labels each published "llm_transaction" with the correct `chat_id`

### Requirement: WebSockets real-time broadcasting

The system SHALL run a WebSockets server that broadcasts all intercepted activity events instantly to all connected dashboard clients.

#### Scenario: Stream event to connected client
- **WHEN** an event is published to the local event bus and a dashboard client is connected via WebSocket
- **THEN** the system encodes the event as JSON and transmits it to the client immediately

### Requirement: Activity monitoring dashboard

The system SHALL serve a web-based dashboard accessible via a standard web browser, showing a listing of active sessions and a real-time, collapsible stream of message exchanges and LLM traces for the selected session.

#### Scenario: Viewing the dashboard
- **WHEN** a user visits the dashboard URL
- **THEN** the system serves a single-page interface showing the active chat sessions and updates the UI dynamically as new events arrive
