## 1. Settings & Configuration

- [x] 1.1 Add Google OAuth2 configuration properties (`CALOBOT_GOOGLE_CLIENT_ID`, `CALOBOT_GOOGLE_CLIENT_SECRET`, `CALOBOT_GOOGLE_REDIRECT_URI`, `CALOBOT_ALLOWED_ADMIN_EMAILS`) to `src/calobot/settings.py` and verify that `get_settings()` loads them correctly in python shell.
- [x] 1.2 Update `.env.example` to document the new Google OAuth2 environment variables and verify that it contains the default admin email `scipio.it@gmail.com`.

## 2. Backend Security & Authentication Layer

- [x] 2.1 Implement cookie-based JWT/token generation and verification helper functions in `src/calobot/telemetry/auth.py` and verify with unit tests that valid signatures are accepted and expired/forged signatures are rejected.
- [x] 2.2 Implement Google OAuth redirect (`/api/auth/login`) and callback (`/api/auth/callback`) routes in `src/calobot/telemetry/server.py` that fetch user email via `httpx2` and verify them against the whitelisted admin emails. Verify with unit tests by mocking Google API responses.
- [x] 2.3 Create a FastAPI dependency or middleware `verify_admin_session` that checks the cookie token, and apply it to `/api/sessions`, `/api/export/{chat_id}`, `/api/sessions/{chat_id}/events`, and the private WebSocket route `/telemetry/ws`. Verify with integration tests that unauthorized requests return `401 Unauthorized`.

## 3. Public Observation & Data Scrubbing

- [x] 3.1 Implement a telemetry event-scrubbing helper in `src/calobot/telemetry/scrub.py` that strips personal information (`username`, `text`, `chat_id` replaced by sequence number, and prompts/responses from LLM logs) and verify with comprehensive unit tests.
- [x] 3.2 Create the unauthenticated endpoint `GET /api/public/metrics` in `src/calobot/telemetry/server.py` to return aggregated stats (latencies, counts) and scrubbed session histories, and verify using integration tests.
- [x] 3.3 Create the public WebSocket route `/telemetry/public/ws` in `src/calobot/telemetry/server.py` to stream real-time scrubbed events, and verify by connecting with a dummy WebSocket client.

## 4. Frontend SPA Router & Split Views

- [x] 4.1 Update `src/calobot/telemetry/frontend/src/App.tsx` to handle route selection dynamically using `window.location.pathname`, serving the public view at `/` and the private view at `/private`. Verify by testing route rendering in local Vite preview.
- [x] 4.2 Build the unauthenticated **Public Dashboard** in `App.tsx` displaying system latencies, request breakdown charts, and the live scrubbed event log. Verify the visual layout against the design.
- [x] 4.3 Move the existing unscrubbed telemetry and model trace viewer to a secure `/private` route, and add a "Sign in with Google" card for unauthenticated clients. Verify that unauthorized visitors cannot see session logs.

## 5. End-to-End Verification

- [x] 5.1 Run the full suite of backend and frontend tests to ensure no regressions in existing logging or telemetry flows. Verify that the build command `npm run build` succeeds in `src/calobot/telemetry/frontend`.
