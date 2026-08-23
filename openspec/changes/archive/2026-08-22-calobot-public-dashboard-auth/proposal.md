## Why

To allow public observation of Calobot's real-time system performance, system operational metrics, and LLM throughput while absolutely protecting user privacy. This change secures all sensitive personal data, user chat histories, and detailed model prompts behind an authenticated private view, while exposing a clean, anonymized public dashboard for public consultation.

## What Changes

- **Public Consultation Dashboard (Unauthenticated)**: A public landing page at `/` serving aggregated system KPIs (e.g., response latencies, request volume, active sessions count) and/or a fully anonymized and scrubbed event log (masking all personal data, usernames, chat IDs, and raw textual parameters).
- **Private Telemetry Suite (Authenticated)**: Moves the existing detailed telemetry stream (raw message logs, Telegram usernames, and complete LLM prompt and completion transaction records) to `/private`.
- **Google OAuth2 Authentication**: Secures `/private` and its supporting `/api/` endpoints (along with WebSocket connections) behind Google OAuth2 login.
- **Access Control Configuration**: Adds settings `CALOBOT_GOOGLE_CLIENT_ID`, `CALOBOT_GOOGLE_CLIENT_SECRET`, `CALOBOT_GOOGLE_REDIRECT_URI`, and `CALOBOT_ALLOWED_ADMIN_EMAILS`, whitelisting the first user `scipio.it@gmail.com` by default.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `realtime-monitor`: Splitting the dashboard requirements into an unauthenticated public view showing anonymized system performance metrics, and a secure private view showing full session traces accessible only to authorized Google-authenticated users.

## Impact

- **Web Server (`src/calobot/telemetry/server.py`)**: Adds session/auth middleware, OAuth callback endpoints, and route protection. Aggregated stats endpoints are added for the public view.
- **Settings (`src/calobot/settings.py`)**: Adds fields for Google Client ID, Client Secret, Redirect URI, and Whitelisted Emails.
- **Frontend SPA (`src/calobot/telemetry/frontend/`)**: Reworks `App.tsx` (or introduces simple path-based routing) to present a public dashboard at `/` and the authenticated monitor at `/private`, with a Google login gateway.
