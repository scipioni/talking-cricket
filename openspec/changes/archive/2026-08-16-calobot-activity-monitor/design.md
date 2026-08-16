## Context

See `proposal.md - Why` and the core capabilities in the specs directory.

Currently, Calobot is structured as an `aiogram` project utilizing `asyncio` for event-loop concurrency. Incoming updates are intercepted by `IncomingLoggingMiddleware` and outgoing responses are caught by `OutgoingLoggingMiddleware` or handled at `Bot.__call__`. LLM calls occur inside `LLMGateway` using the asynchronous `openai` client. 

To introduce a highly responsive, modern, real-time web monitoring interface, we will implement a Single Page Application (SPA) using **Vite, React, and Tailwind CSS v4**, served natively from our Python web process via FastAPI's StaticFiles.

## Goals / Non-Goals

**Goals:**
- Provide zero-latency, asynchronous event broadcasting for bot and LLM interactions.
- Establish precise causal correlation between an incoming user message and any subsequent downstream LLM calls (structured classification, extraction, etc.) using `contextvars`.
- Serve a modern, reactive single-page dashboard built with React and Tailwind CSS v4.
- Enable high-fidelity real-time updates on the UI using browser-native WebSockets connected directly to FastAPI.
- Keep the production container image clean of Node.js and compile dependencies using a multi-stage Docker build.
- Provide a structured API endpoint (`/api/export/{chat_id}`) that outputs the complete history of any active session for agent evaluation.

**Non-Goals:**
- Persisting high-volume debug logs/completions into the main SQLite database for long periods (to avoid database bloating and single-writer lock contention). Telemetry history will live in memory, structured inside a thread-safe, size-bounded buffer.
- Running a persistent Node.js dev server or running Node.js at runtime in production. Node.js is strictly used during the compilation step.

## Decisions

### Decision 1: Thread-Safe Telemetry Event Bus (PubSub)
We will introduce a central `TelemetryEventBus` in `src/calobot/telemetry/bus.py`.
* **Mechanism**: When an event (incoming text, outgoing reply, LLM request/response) occurs, it is dispatched to the event bus using non-blocking calls (`asyncio.create_task`).
* **Distribution**: The bus keeps a list of active asyncio queues representing WebSocket connections. When an event is published, it is pushed to all active subscriber queues.
* **Why**: An in-memory queue is extremely fast, uses no external dependencies (like Redis/RabbitMQ), and respects the non-blocking nature of asyncio.

### Decision 2: Causal Correlation via `contextvars`
We will introduce `src/calobot/telemetry/context.py` containing a `ContextVar`:
```python
import contextvars
active_chat_id: contextvars.ContextVar[int] = contextvars.ContextVar("active_chat_id")
```
* **Integration**:
  - `IncomingLoggingMiddleware` binds the current update's `chat_id` into `active_chat_id` before invoking the main router.
  - When `LLMGateway` executes a call, it reads `active_chat_id.get(fallback=None)` to automatically associate the prompt/completions with that specific chat session.
* **Why**: Since `contextvars` are task-local, they naturally flow across any asynchronous boundaries, including multi-task spawns and sub-calls, without having to pollute internal service signatures with `chat_id` arguments.

### Decision 3: Serve Vite Production Build Natively from FastAPI
We will house the frontend workspace inside `src/calobot/telemetry/frontend/`.
* **Build-time Output**: In production, Vite compiles the React code and Tailwind styles into static assets under `src/calobot/telemetry/frontend/dist/`.
* **FastAPI Mounting**: FastAPI will mount this `dist/` directory as static files and serve the SPA's entry point:
  ```python
  from fastapi.staticfiles import StaticFiles
  
  app.mount("/", StaticFiles(directory="src/calobot/telemetry/frontend/dist", html=True), name="static")
  ```
* **Why**: Guarantees zero runtime performance overhead, completely avoids CORS issues, and keeps deployment restricted to a single port and single running replica.

### Decision 4: Tailwind CSS v4 compiler setup
We will style the interface using **Tailwind CSS v4** which features a modern, ultra-fast CSS-first compilation engine.
* **Vite Integration**: We use `@tailwindcss/vite` as a Vite plugin inside `vite.config.ts`.
* **Configuration**: Since Tailwind v4 is CSS-first, we do not require a separate `tailwind.config.js`. Instead, all custom fonts, colors, and keyframes are declared directly using native `@theme` directives inside the main entry stylesheet (`src/index.css`):
  ```css
  @import "tailwindcss";
  
  @theme {
    --color-bot-blue: #1e3a8a;
    --color-user-green: #064e3b;
  }
  ```
* **Why**: CSS-first configuration is cleaner, compiles significantly faster, and simplifies the codebase by eliminating legacy JavaScript-based configuration files.

### Decision 5: Bounded Telemetry Deque per Session
* **Mechanism**: The telemetry engine maintains an in-memory `collections.defaultdict(lambda: collections.deque(maxlen=100))` mapping `chat_id` to its most recent 100 interaction events.
* **Exporting**: When `/api/export/{chat_id}` is hit, the system queries this in-memory deque, groups the events, and formats them into the unified JSON timeline schema.
* **Why**: High performance, zero SQLite disk writes, and prevents unbounded memory growth.

### Decision 6: Docker Multi-Stage Build
* **Stage 1 (Frontend Build)**:
  - Node alpine image. Installs npm packages under `/frontend` and runs `npm run build` to generate `/frontend/dist`.
* **Stage 2 (Python Runtime)**:
  - Base Python image. Runs migrations, installs dependencies with `uv`.
  - Copies `/frontend/dist` from Stage 1 into `/src/calobot/telemetry/frontend/dist`.
* **Why**: Keeps the final production container extremely slim, secure, and isolated from Node.js dependencies.

## Risks / Trade-offs

- **[Risk] Port conflicts on host machine during deployment.**
  * *Mitigation*: The web server port will default to `8080`, and will be fully configurable via `CALOBOT_WEB_PORT` environment variable.
- **[Risk] Production image size bloat from React/Node build tools.**
  * *Mitigation*: Solved completely by the multi-stage Docker build; no Node.js runtime or build-time dependencies exist in the final Python container.
- **[Risk] Telemetry memory leak over extremely long sessions.**
  * *Mitigation*: Handled by size-bounded `deques` with a strict limit of 100 events per session.
