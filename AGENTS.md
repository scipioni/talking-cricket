# Agent instructions

## Project

Calobot ("Talking Cricket") is a Telegram virtual nutritionist bot: users log food,
weight and activity in free-form Italian chat; an LLM classifies and extracts
structured data, deterministic code validates/computes/stores it, and reports come
back as charts. Full rationale and specs live in
`openspec/changes/calobot-v1/` (proposal, design, specs, tasks) — read that before
making behavioral changes, and update the relevant spec/tasks file alongside any
change that alters observable behavior.

## Commands

Prefer the `Taskfile.yml` wrappers over raw commands:

- `task setup` — `uv sync` into `.venv`
- `task dev` — run the bot locally (migrations + seed + polling), reads `.env`
- `task test` / `task lint` / `task typecheck` / `task check` (all three)
- `task migration -- "message"` — new Alembic revision (never use `create_all`)
- `task docker:build`, `task docker:publish` (needs `DOCKERHUB_NAMESPACE=...`)
- `task release:patch` / `:minor` / `:major` — bump version, commit, tag locally
  (does not push); `task release:push` does that explicitly afterward

## Conventions

- When creating git commits, do not add a `Co-Authored-By` trailer.
- Never call `Base.metadata.create_all`; schema changes go through Alembic
  (`task migration -- "..."`).
- Entries (food/activity/weight) are soft-deleted (`deleted_at`); every read path
  must filter it. `/cancellami` is the one intentional hard-delete.
- All day-boundary logic takes a timezone as a parameter (`Europe/Rome` by
  default) — never hardcode it, so per-user timezones stay a one-line change later.
- LLM calls go through `calobot.llm.gateway.LLMGateway.call_structured` only, with
  a small flat Pydantic schema per call — this model degrades on nested/union
  schemas, so prefer two small calls over one clever one.
- Keep `src/calobot/data/DATA_SOURCES.md` accurate: only CC0/public-domain data is
  bundled in the image (CREA and the Compendium of Physical Activities were
  deliberately rejected on licensing grounds — do not reintroduce them).
- `mypy` is intentionally not `strict`; see the per-module overrides and comment
  in `pyproject.toml` before adding new suppressions.
- Tests use an in-memory SQLite session (`tests/conftest.py`) and a stubbed LLM
  gateway — no live network/model access needed to run the suite.
