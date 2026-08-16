## Why

As Calobot operates as a Telegram conversational agent, its internal state transitions, message ingestion steps, and underlying LLM completions (including prompts, system templates, temperature, structured JSON schemas, and multi-turn retries) are completely invisible from the outside. Observing the bot in production currently requires analyzing raw application logs, and there is no way to inspect live sessions or trace the precise reasoning path of the model for a specific turn in real time.

Furthermore, optimizing Calobot's prompt engineering, safety guards, and classification accuracy requires a high-fidelity dataset of real chatbot interactions. Currently, there is no standardized way to extract full conversation sessions (including user inputs, bot replies, and raw LLM payloads) in a structured format suitable for offline analysis by developers or automated engineering agents.

This change adds a live, real-time web dashboard for observability and prompt-tracing, and provides a structured session-export capability to support offline agentic analysis.

## What Changes

- **In-process Event Bus / PubSub**: A lightweight, non-blocking asynchronous event bus that captures incoming updates, outgoing bot replies, and raw LLM gateway transactions (request body, schema, response JSON, errors, and validation retries) across the application lifecycle.
- **`contextvars` Integration**: A context manager that associates all concurrent and downstream async tasks spawned by a single Telegram update with its originating `chat_id` and `session_id`, ensuring correct event causal tracing.
- **FastAPI / Uvicorn Integration**: Run a lightweight web server alongside the main Telegram polling loop using `asyncio.gather`. The web server hosts:
  - A real-time web dashboard showing active chat sessions and live event streams.
  - A REST API to fetch active session lists and retrieve structured session histories.
- **Vite + React + Tailwind CSS v4 SPA**: A modern web-based monitoring console built using React, bundled via Vite, and styled using Tailwind CSS v4.
- **Unified Session Export**: An endpoint (`/api/export/{chat_id}`) that outputs a complete, deterministic, and chronologically ordered JSON schema of the session's entire lifecycle. This includes user text/images, bot replies with inline keyboards, and the precise sequence of LLM calls, prompts, and raw responses.

## Capabilities

### New Capabilities

- `realtime-monitor`: The core specifications for event interception, real-time WebSockets broadcasting, live session dashboard layout, and the telemetry contract.
- `activity-export`: The specifications for the unified session activity schema, export API, and standard JSON representation for agent analysis.

### Modified Capabilities

None. This change introduces pure observability, monitoring, and export capabilities without changing any existing bot conversational behaviors or persisting production user data differently.

## Impact

- **New dependencies**:
  - Backend: `fastapi` and `uvicorn` (with `websockets` or any standard ASGI server requirements) to run the concurrent web application.
  - Frontend (Build-time only): Node.js, `npm`, `vite`, `react`, `tailwindcss` v4, and `@tailwindcss/vite` plugin.
- **Modified components**: 
  - `src/calobot/main.py`: Modified to concurrently run both the `Dispatcher` polling loop and the `FastAPI` / `Uvicorn` web server on the same event loop.
  - `src/calobot/llm/gateway.py`: Modified to publish LLM request/response events to the Event Bus, associated with the current task's contextual `chat_id`.
  - `src/calobot/telegram/logging_middleware.py`: Modified to publish IN/OUT Telegram messages to the Event Bus.
  - `Dockerfile`: Redesigned to support a **multi-stage build**. Stage 1 installs Node.js and builds the frontend assets using Vite into a `dist/` folder. Stage 2 sets up the Python environment and copies the compiled static assets into the Python image, ensuring no Node.js runtime footprint in production.
- **Concurrency & SQLite Single-Writer**: The web application reads session activities purely from memory-buffered logs or a separate logging table. To respect the single-writer SQLite constraint, any database logging of telemetry will utilize a shared session-factory or stay memory-buffered.
- **Security & Privacy**: The web dashboard is password-protected or restricted to local/admin networks to prevent unauthorized access to sensitive conversation logs.
