## Why

Tracking food intake, weight and movement is the single most effective habit for reaching a weight goal, but every existing tool demands structured data entry: search a database, pick a portion, tap a number. People abandon them within weeks. An LLM removes that friction entirely — the user writes *"ho mangiato 10g di noci"* or *"oggi peso 78kg"* in a Telegram chat they already have open, and the system does the structuring.

Calobot is that bot: a virtual nutritionist that turns free-form Italian chat into a rigorous energy and weight log, and gives back charts that make the trend visible.

## What Changes

This is the initial build — everything below is new.

- **Telegram bot** (aiogram 3), autoregistering the user on `/start`.
- **Conversational onboarding** collecting sesso, data di nascita, altezza, peso attuale, peso obiettivo, livello di attività and ritmo desiderato; free text for values, inline keyboards for enums, resumable across restarts.
- **Daily calorie budget** derived from the profile: `BMR (Mifflin-St Jeor) × fattore_attività − deficit(ritmo)`, with a safety floor.
- **Message ingestion pipeline**: classify-then-extract. Every inbound message is classified (`food` / `weight` / `activity` / `correction` / `report` / `other`), then extracted into a typed draft with a small flat schema, validated with Pydantic and retried on failure.
- **Clarification loop**: when a draft is not processable (missing grams, missing intensity), the bot asks — offering common answers as inline buttons — and merges the reply into the pending draft. Drafts are persisted, so they survive a container restart.
- **Food logging** with a hybrid kcal resolver: normalized-name cache → bundled food composition table (candidates retrieved by fuzzy search over an Italian alias index, LLM picks the row) → LLM estimation for composite dishes. Every resolution is cached with its provenance (`table` / `llm`) so the same dish always costs the same.
- **Activity logging** using a bundled MET table: `kcal = MET × peso_attuale × ore`. Activity is **informational only** — it never alters the daily budget (energy model B), because the activity factor in the profile already accounts for habitual movement.
- **Weight logging**, with the LLM normalizing conversational forms (*"78 e mezzo"*, *"sono sceso a 77"*) into a precise value.
- **Corrections**: `/annulla` for the last entry, plus inline `modifica` / `elimina` buttons and Telegram reply-to targeting on every confirmation message, so *which* entry is being corrected is resolved deterministically and the LLM only interprets *what* changes. Entries are soft-deleted.
- **Reports and charts** over day / week / month / year, rendered as PNG images: weight with a 7-day moving average, goal line and trend projection; calories as bars against the target line; activity minutes per period.
- **Safety guardrails**: minimum calorie floor, refusal to set targets outside safe ranges, no medical advice, explicit non-medical disclaimer at onboarding.
- **Platform**: Python managed by `uv` with a `pyproject`/src layout, SQLAlchemy 2.0 + Alembic migrations over SQLite in WAL mode, all timestamps in `Europe/Rome`, multi-stage Dockerfile deployed to Docker Swarm as a single replica with a pinned volume.

Explicitly **out of scope for v1** (doors deliberately left open): photo/barcode input — although the configured model is vision-capable and the extraction layer accepts `text | image` from day one — free-text corrections of historical entries (*"ieri a pranzo"*), automatic recalibration of the activity factor, multi-language support beyond Italian.

## Capabilities

### New Capabilities

- `user-profile`: registration on `/start`, conversational onboarding, profile fields and their validation, BMR/TDEE/budget computation, safety floors, profile editing.
- `message-ingestion`: the classify-then-extract pipeline, draft lifecycle, the clarification loop and its termination rules, LLM invocation contract (schema validation, retry, graceful failure), and the `text | image` input contract.
- `food-logging`: food entry semantics, the hybrid kcal resolution chain, the resolution cache and provenance, portion handling.
- `activity-logging`: activity entry semantics, MET-based energy computation, intensity clarification, and the rule that activity never alters the budget.
- `weight-logging`: weight entry semantics, conversational value normalization, plausibility validation, one-per-day handling.
- `entry-correction`: undo, amend and delete semantics; deterministic entry targeting via buttons and reply-to; soft-delete behaviour and its effect on reports.
- `reporting`: report periods, the metrics each report contains, chart rendering rules (moving average, goal line, projection), and empty/sparse-data behaviour.

### Modified Capabilities

None — this is a greenfield project with no existing specs.

## Impact

- **New repository content**: entire Python application (`src/` layout), Alembic migration chain, bundled seed datasets, Dockerfile and Swarm stack file.
- **Seed data licensing**: only sources that permit redistribution inside a container image are bundled — a USDA FoodData Central subset (US government work, public domain, no obligations) for foods, plus an own-compiled Italian MET table. The CREA tables are deliberately not used: they carry no open licence, and in the EU their compilation is additionally protected by the *sui generis* database right.
- **Runtime dependencies**: Telegram Bot API; an OpenAI-compatible LLM endpoint — initially the self-hosted `https://ingegno.csgalileo.org/ollama/v1` with `qwen3-vl:30b-a3b-instruct`, with base URL, model, temperature and timeout all configurable per task.
- **Python dependencies**: aiogram 3, SQLAlchemy 2.0, Alembic, Pydantic, an OpenAI-compatible client, matplotlib (image size and font handling must be budgeted in the Dockerfile).
- **Data**: stores personal health data (weight, age, sex, height, eating and activity habits) in a single SQLite file on a Swarm volume. Retention, backup and deletion (`/cancellami`) must be addressed.
- **Deployment constraint**: SQLite permits exactly one writer. The Swarm service must be pinned to `replicas: 1` with a placement constraint and a local volume; scaling it horizontally would silently diverge data.
