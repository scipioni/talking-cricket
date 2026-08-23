## MODIFIED Requirements

### Requirement: Activity monitoring dashboard
The system SHALL serve a web-based private dashboard accessible only to authorized, authenticated users, showing a detailed listing of active sessions and a real-time, collapsible stream of unscrubbed message exchanges and LLM traces for the selected session.

#### Scenario: Viewing the dashboard
- **WHEN** an authenticated user whose email is whitelisted visits `/private`
- **THEN** the system serves the full, detailed telemetry stream of active chat sessions and updates the UI dynamically as new events arrive

#### Scenario: Unauthorized user accesses the private dashboard
- **WHEN** an unauthenticated visitor or an authenticated user with a non-whitelisted email visits `/private` or accesses private endpoints (e.g., `/api/sessions`, `/api/export/*`, `/telemetry/ws`)
- **THEN** the system redirects them to the login flow or returns a `403 Forbidden` error

## ADDED Requirements

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
