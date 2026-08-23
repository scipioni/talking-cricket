# realtime-monitor Specification

## Purpose

Intercepts all user messages, bot responses, and raw LLM completions in real time to broadcast them over WebSockets to an interactive monitoring dashboard.

## Requirements

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
The system SHALL serve a web-based private dashboard accessible only to authorized, authenticated users, showing a detailed listing of active sessions and a real-time, collapsible stream of unscrubbed message exchanges and LLM traces for the selected session.

#### Scenario: Viewing the dashboard
- **WHEN** an authenticated user whose email is whitelisted visits `/private`
- **THEN** the system serves the full, detailed telemetry stream of active chat sessions and updates the UI dynamically as new events arrive

#### Scenario: Unauthorized user accesses the private dashboard
- **WHEN** an unauthenticated visitor or an authenticated user with a non-whitelisted email visits `/private` or accesses private endpoints (e.g., `/api/sessions`, `/api/export/*`, `/telemetry/ws`)
- **THEN** the system redirects them to the login flow or returns a `403 Forbidden` error

### Requirement: Public consultation dashboard
The system SHALL serve an unauthenticated, public web dashboard showing aggregated operational KPIs and completely anonymized/scrubbed event activity to protect user privacy.

#### Scenario: Public visitor views the dashboard
- **WHEN** an anonymous user visits `/`
- **THEN** the system serves a public dashboard displaying aggregated metrics (active session count, average LLM latency, processing volume by intent) and a real-time stream of fully scrubbed events with no personal data

### Requirement: Google OAuth2 authentication
The system SHALL enforce secure Google OAuth2 login to authenticate admin access to private endpoints, comparing the verified user email against the whitelisted administrators list.

#### Scenario: Successful admin authentication
- **WHEN** a user completes Google OAuth2 login and their email matches the whitelist configuration
- **THEN** the system issues a secure session token and grants access to `/private` and supporting private API endpoints
