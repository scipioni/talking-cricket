## Context

See `proposal.md` — Why. Currently, `src/calobot/telemetry/server.py` runs a FastAPI app serving unauthenticated observation endpoints (`/api/sessions`, `/api/export/{chat_id}`, `/api/sessions/{chat_id}/events`, and the WebSockets `/telemetry/ws`), alongside static assets built from the React SPA. To split this dashboard, we must introduce security controls that restrict access to conversational text and prompts while maintaining an open dashboard for public consultation.

```
+---------------------------------------------------------------------------------+
|                               SYSTEM ARCHITECTURE                               |
+---------------------------------------------------------------------------------+

                      ANONYMOUS PUBLIC CLIENT
                                │
                                ▼ (Serves Static SPA Index)
                    ┌─────────────────────────┐
                    │  FastAPI Router (/)     │
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │ GET /api/public/metrics │ (Public aggregated operational metrics)
                    │ ws://.../telemetry/pub  │ (Public anonymized WebSocket stream)
                    └─────────────────────────┘

                     GOOGLE AUTHENTICATED ADMIN
                                │
                                ▼ (Secure HTTP-Only Cookie Validation)
                    ┌─────────────────────────┐
                    │ FastAPI Router (/priv)  │ (Guarded: redirects to Google OAuth if no session)
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │  GET /api/sessions      │ (Raw conversational logs)
                    │  GET /api/export/*      │ (Full model completions)
                    │  ws://.../telemetry/ws  │ (Full private WebSockets)
                    └─────────────────────────┘
```

## Goals / Non-Goals

**Goals:**
- Secure the existing detailed observation views, raw text telemetry, and WebSocket endpoints behind a Google OAuth2 layer.
- Restrict access to whitelisted admin emails, starting with `scipio.it@gmail.com`.
- Expose a public landing page at `/` serving aggregated KPIs and scrubbed event metrics without exposing any personal data.
- Enforce backend security: block API and WebSocket requests to private telemetry assets if the client does not present a valid, authorized session cookie.

**Non-Goals:**
- Implementing fully fledged database-backed user registration (admins are simple whitelist-controlled records parsed from settings).
- Supporting multiple OAuth2 providers (limited strictly to Google Authentication).
- Tracking multi-tenant user permissions (access is binary: either a user is an authorized admin or they are not).

## Decisions

### Decision 1: Cookie-Based JWT Session Management
We will use a secure, HTTP-Only, SameSite-lax signed session cookie on the FastAPI backend containing a simple JWT-like token.
- **Why**: Cookie-based sessions are automatically handled by browser page loads and WebSockets alike, eliminating the need to pass custom headers or tokens inside raw WS protocol handshakes.
- **Mechanism**: On successful Google OAuth callback, the backend signs a payload `{"email": "scipio.it@gmail.com", "exp": <timestamp>}` using HMAC-SHA256 with a secret key loaded from `CALOBOT_SESSION_SECRET` (or dynamically generated at startup if unconfigured).
- **Alternative considered**: Bearer token authentication. Rejected because authenticating raw browser WebSocket handshakes via headers is not native (browsers do not allow setting custom headers on `new WebSocket(...)`), which would require complex sub-protocol negotiation.

### Decision 2: Routing Split & Static Asset Guarding
We will reorganize static serving to protect private assets while leaving public views open:
- `/` serves public index and public assets.
- `/private` serves the private React dashboard. The backend route `GET /private` checks for a valid session cookie first; if missing, it redirects to `/api/auth/login`. This ensures the private JS bundle itself cannot be downloaded by unauthenticated users.
- **Why**: Restricting frontend source downloads is a security best-practice when the frontend source contains administrative interface code.

### Decision 3: Anonymization & Public Telemetry endpoints
We will implement two distinct telemetry channels:
1. **Private Endpoints**: `/api/sessions`, `/api/sessions/{chat_id}/events`, `/api/export/{chat_id}`, `/telemetry/ws` (Guarded by session verification).
2. **Public Endpoints**:
   - `GET /api/public/metrics`: Computes and returns aggregated counters (active sessions count, total logs by intent) and average latencies from the memory collector. It also returns a bounded list of recent event headers completely stripped of `username`, `chat_id` (replaced with anonymous indices), and all textual messages.
   - `ws://.../telemetry/public/ws`: A dedicated WebSocket endpoint that broadcasts events with user and bot text replaced by semantic summaries (e.g., `[User Logged Food]`), and LLM text payloads omitted entirely.
- **Why**: Decoupling the data pipeline into clear public/private routes guarantees zero risk of accidental text leakage through unscrubbed telemetry.

### Decision 4: Configuration of Allowed Emails
- We will add the settings `CALOBOT_GOOGLE_CLIENT_ID`, `CALOBOT_GOOGLE_CLIENT_SECRET`, and `CALOBOT_ALLOWED_ADMIN_EMAILS` to `src/calobot/settings.py`.
- `CALOBOT_ALLOWED_ADMIN_EMAILS` is a string list parsed as a comma-separated array or a JSON list, default-populating with `["scipio.it@gmail.com"]`.

## Risks / Trade-offs

- **[Risk] State parameter forgery / CSRF on OAuth callback** -> *Mitigation*: We will use a signed `state` cookie generated during redirect and verified during callback to prevent login CSRF attacks.
- **[Risk] Cookie size boundaries** -> *Mitigation*: The JWT session cookie only carries the email address and expiry timestamp, keeping the payload under 200 bytes (well within the browser's 4KB cookie limit).
- **[Risk] Google OAuth credentials unconfigured** -> *Mitigation*: If Google Client ID or Secret are missing at startup, the server will log a clear warning and gracefully disable the `/private` login redirect, returning a helpful setup screen rather than raising unhandled exceptions.
