## 1. Setup and Dependencies

- [x] 1.1 Add backend dependencies (`fastapi`, `uvicorn`) to `pyproject.toml`
- [x] 1.2 Scaffold React app with Vite inside `src/calobot/telemetry/frontend/`
- [x] 1.3 Install Tailwind CSS v4 (`tailwindcss`, `@tailwindcss/vite`) in the React frontend workspace
- [x] 1.4 Configure `vite.config.ts` to use `@tailwindcss/vite` and setup `src/index.css` with `@import "tailwindcss";`

## 2. Telemetry Core: Event Bus & Context

- [x] 2.1 Implement async `TelemetryEventBus` in `src/calobot/telemetry/bus.py` for publishing/subscribing to events
- [x] 2.2 Implement task-local `active_chat_id` and `active_session_id` using `contextvars` in `src/calobot/telemetry/context.py`
- [x] 2.3 Implement thread-safe `InMemoryTelemetryHistory` using bounded deques in `src/calobot/telemetry/history.py`

## 3. Integration Points

- [x] 3.1 Instrument `IncomingLoggingMiddleware` to set context variables and publish `"incoming_update"` events
- [x] 3.2 Instrument `OutgoingLoggingMiddleware` to publish `"outgoing_response"` events
- [x] 3.3 Instrument `LLMGateway` to extract contextual `chat_id` and publish detailed `"llm_transaction"` events containing the prompts, model parameters, and raw JSON schemas

## 4. FastAPI Web Server & React Dashboard

- [x] 4.1 Define FastAPI app with WebSocket broadcasting endpoint in `src/calobot/telemetry/server.py`
- [x] 4.2 Implement GET `/api/export/{chat_id}` endpoint that aggregates the deque history into the unified JSON schema
- [x] 4.3 Build the React Dashboard displaying active chat sessions on the sidebar, conversation bubbles in the main pane, and interactive collapsible tracing cards for each LLM step
- [x] 4.4 Configure FastAPI to serve the compiled React SPA static folder (`frontend/dist/`) via `StaticFiles`
- [x] 4.5 Modify `src/calobot/main.py` to launch both `Dispatcher` polling and `uvicorn` concurrently on the same loop using `asyncio.gather`

## 5. Testing & Production Configuration

- [x] 5.1 Create unit tests for telemetry event bus, context-propagation, and bounded history deques
- [x] 5.2 Create integration tests for the FastAPI WebSocket connections and HTTP `/api/export/{chat_id}` endpoint
- [x] 5.3 Redesign `Dockerfile` as a multi-stage Docker build, where Stage 1 builds the Vite app and Stage 2 copies the compiled static assets into the Python image
- [x] 5.4 Run verification suite (`pytest`, `ruff check`, and `mypy`) to confirm zero regressions
