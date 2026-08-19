# Calobot

*Also known as "Talking Cricket" (il Grillo Parlante) — the little voice that keeps
you honest about what you eat.*

A Telegram virtual nutritionist. Log food, weight and activity in free-form Italian
chat, or by pointing a camera at it; an LLM structures the message, deterministic
code validates and computes the numbers, and reports come back as charts.

See `openspec/changes/archive/2026-08-16-calobot-v1/` for the full proposal, design
rationale and specs behind the text-based build,
`openspec/changes/archive/2026-08-17-calobot-photo-input/` for the photo feature
(nutrition labels, barcodes, dish photos) layered on top of it, and
`openspec/changes/archive/2026-08-17-calobot-advice-agent/` for the read-only agent
that answers open-ended questions about a user's own data.

## How it works, in one paragraph

Every inbound message is classified into an intent (food / weight / activity /
correction / report / other), then extracted into a small typed schema by the
configured LLM. If something required is missing (a portion size, a duration), the
bot asks - with tappable buttons for the common answers - and merges the reply into
a draft persisted in the database, so a restart mid-conversation doesn't lose it.
Food and activity energy values are resolved through a cache, then a bundled lookup
table (the model picks the best matching row), then a model estimate as a last
resort - so the same food always costs the same the next time it's logged. A photo
is classified as a nutrition label, a barcode, or a dish, and each writes its energy
value into that same cache (with its own provenance and trust ranking, highest for
a label, lowest for a model estimate), then joins the same draft/clarification flow
as a typed message.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An OpenAI-compatible LLM endpoint (defaults to a self-hosted Ollama instance
  running `qwen3-vl:30b-a3b-instruct`)
- The `zbar` shared library for barcode decoding (`libzbar0` on Debian/Ubuntu,
  `zbar` via Homebrew) - `pyzbar` binds to it via ctypes rather than a wheel, so it
  isn't something `uv sync` alone can provide. Already installed in the Docker image.

## Local development

There's a `Taskfile.yml` ([go-task](https://taskfile.dev)) wrapping the commands
below - `task --list` shows everything. The quick path:

```bash
task setup                    # uv sync into .venv
cp .env.example .env          # fill in CALOBOT_TELEGRAM_BOT_TOKEN at minimum
task dev                      # migrations + seed + long polling, restarts on code changes
```

`task dev` watches `src/` (via [`watchfiles`](https://watchfiles.helpmanual.io/))
and restarts the whole process - a fresh migrate/seed/reconnect cycle - whenever a
file changes. That's a full bot restart, not a hot code swap: any in-flight
conversation is interrupted (Telegram just redelivers on reconnect, so it's not
lossy, just not seamless). Use `task dev:once` to run without watching.

The equivalent without Task, run by hand - note `.env`'s `CALOBOT_DATABASE_PATH`
points at the Docker container's `/data` mount, which doesn't exist outside a
container, so override it for a local run:

```bash
uv sync
set -a && source .env && set +a
export CALOBOT_DATABASE_PATH=./data/calobot.db
uv run watchfiles calobot.main.run src   # or: uv run python -m calobot.main (no watch)
```

Running the test suite (uses an in-memory SQLite database, no external services):

```bash
task test        # or: uv run pytest
task lint         # or: uv run ruff check src/ tests/ scripts/
task typecheck    # or: uv run mypy src/
task check        # all three
```

`task test` never contacts the language model, and drives the real Telegram handlers
through an in-process stand-in for the client, so taps, entry controls, replies and
commands are covered rather than only text. Separately, `task simulate` runs an agent
that plays an uncooperative user across simulated days against the real endpoint -
slow and it costs compute, so it is opt-in. See [docs/e2e.md](docs/e2e.md).

All configuration is environment-driven; see `.env.example` for the full list.
Notably:

- `CALOBOT_LLM_BASE_URL` / `CALOBOT_LLM_MODEL` / `CALOBOT_LLM_TEMPERATURE` /
  `CALOBOT_LLM_TIMEOUT_SECONDS` / `CALOBOT_LLM_RETRY_LIMIT` configure the gateway.
- `CALOBOT_LLM_CLASSIFY_MODEL` / `CALOBOT_LLM_CLASSIFY_TEMPERATURE` and the
  `_EXTRACT_` equivalents override the classify/extract pipeline steps
  independently, so classification can run on a smaller/faster model later
  without a code change.
- `CALOBOT_DATABASE_PATH` defaults to `/data/calobot.db` (the Docker volume mount
  point); point it elsewhere for local development.
- `CALOBOT_TIMEZONE_NAME` defaults to `Europe/Rome` and governs every day boundary
  (reports, "one weight per day", etc).
- `CALOBOT_DRAFT_EXPIRY_MINUTES` and `CALOBOT_CLARIFICATION_ATTEMPT_LIMIT` bound an
  open clarification: the first by time, the second by how many consecutive
  unusable answers the bot accepts before dropping the draft and saying so.

### Adding migrations

Never call `Base.metadata.create_all`; always go through Alembic:

```bash
task migration -- "describe the change"   # or: uv run alembic revision --autogenerate -m "..."
task migrate                              # or: uv run alembic upgrade head
```

### Seed data

`src/calobot/data/` bundles a food-energy table and a MET (activity) table, both
described and licensed in `src/calobot/data/DATA_SOURCES.md` - read that file before
touching either dataset, especially before considering swapping in CREA or the
Compendium of Physical Activities, both of which were deliberately rejected on
licensing grounds. `scripts/generate_aliases.py` regenerates the Italian alias index
for the food table via the configured LLM.

## Deploying to Docker Swarm

```bash
docker build -t calobot:latest .

# the stack pins the service to a specific node so its local volume is stable -
# label that node first:
docker node update --label-add calobot-data=true <node-id>

docker stack deploy -c stack.yml calobot \
  --with-registry-auth
```

Set `CALOBOT_TELEGRAM_BOT_TOKEN` (and any LLM overrides) in the shell environment
before `docker stack deploy`, or via a `.env` file consumed by your deploy tooling -
`stack.yml` reads them from the environment.

**Do not scale this service past one replica.** SQLite allows exactly one writer;
running two replicas against the same volume will silently corrupt or diverge data.
This is enforced in three places: `stack.yml` pins `replicas: 1` with a placement
constraint, the named volume uses the `local` driver (never point it at NFS/CIFS -
SQLite locking is unreliable there), and the application itself
(`calobot.persistence.startup_checks`) refuses to start if it detects the database
directory sits on a network filesystem.

### Backup and restore

The entire application state - every user, entry and cached resolution - lives in
one SQLite file on the `calobot_data` volume. **Losing that volume is losing
everything**; back it up like you would any production database, not like a
disposable container.

```bash
# backup (safe to run while the container is up - SQLite is in WAL mode)
docker run --rm -v calobot_data:/data -v "$(pwd)":/backup alpine \
  sh -c "cp /data/calobot.db /data/calobot.db-wal /data/calobot.db-shm /backup/ 2>/dev/null; true"

# restore onto a fresh volume
docker run --rm -v calobot_data:/data -v "$(pwd)":/backup alpine \
  cp /backup/calobot.db /data/calobot.db
```

Schedule the backup step on a cron/timer outside the cluster; this repository does
not include a backup automation, only the mechanism.

## Bot commands

| Command | Behaviour |
|---|---|
| `/start` | Register (first time) or resume/show status |
| `/profilo` | Show the stored profile and current daily calorie budget |
| `/annulla` | Delete the most recently logged entry |
| `/cancellami` | Permanently delete all of your data (hard delete, not soft) |
| `/help` | List the available commands |

Everything else is free-form Italian chat: log food ("ho mangiato 10g di noci"),
weight ("oggi peso 78kg"), activity ("camminata di mezz'ora"), corrections ("no
erano 20g" - or reply directly to the confirmation message), or ask for a report
("report di questa settimana").

You can also just send a photo instead of typing:

- **A nutrition label** is read directly (energy per 100 g, product name where
  legible) - the most accurate input the system accepts, and it teaches the system
  that product permanently: a later typed mention of the same product resolves from
  the same reading.
- **A barcode** is decoded locally and looked up against
  [Open Food Facts](https://openfoodfacts.org) (data used under ODbL, attributed in
  the confirmation).
- **A photo of a dish** identifies the foods on the plate, one draft each.

A photo never establishes quantity by itself - it still asks "quanto?" for each
food, the same one-tap clarification a typed message gets. Photos are processed and
discarded; nothing is written to disk. See
`openspec/changes/archive/2026-08-17-calobot-photo-input/` for the full design.

## Asking questions about your own data

A message that is not a log, a correction or a report request ("come sono andato
questa settimana?", "posso permettermi una pizza stasera?") goes to a read-only
advice agent instead of a plain conversational reply. It works in two bounded steps:

1. **Gather** - the model may call a small, whitelisted set of read-only tools (each
   wrapping the same deterministic aggregator that produces a report or chart) up to
   `CALOBOT_LLM_ADVICE_MAX_ROUNDS` times (default 4). Whose data it reads is bound to
   the sender's Telegram identity outside the conversation - no tool accepts a user
   identifier, so no message can redirect it to someone else's diary.
2. **Narrate** - one schema-constrained call turns whatever was retrieved into the
   Italian reply. The model never computes a figure itself; every number it states
   is the one a tool returned, so an answer for a period cannot disagree with a
   report for the same period. When the data needed doesn't exist - nothing logged
   in the period, or a quantity the bot doesn't track (macronutrients, for instance)
   - it says so instead of estimating.

The agent cannot create, edit or delete anything: it is confined to the same
read-only tools regardless of what a message asks for, and a reply that claims a
record was made, changed or removed is suppressed and replaced. The existing medical
and eating-disorder refusal runs before the agent does anything, exactly as it does
on the plain conversational path. See `docs/agent.md` for the tool catalog, a worked
example, and how to add a tool, and
`openspec/changes/archive/2026-08-17-calobot-advice-agent/` for the full design and
the requirements each of these behaviours traces to.

## Advanced Logging & Development Features

### JSONL Interaction Logger
A structured JSONL turn-level interaction logger is available to capture and record the complete history of all user chats, outbound bot replies, and gateway LLM transactions.
* **Format:** Every logical user interaction (the entire message turn, including all intermediate steps, prompts, retries, and API calls) is compiled and serialized as exactly **one row** of structured JSON data.
* **Performance:** Writing to the log file is fully asynchronous and offloaded to a non-blocking background thread pool (`asyncio.to_thread`) to prevent blocking the asyncio event loop.
* **Configuration:**
  * `CALOBOT_JSONL_LOG_ENABLED` (boolean, defaults to `True`): Toggles the JSONL interaction logger.
  * `CALOBOT_JSONL_LOG_PATH` (string, defaults to `/data/interactions.jsonl`): Sets the destination path for the JSONL file.

### Persistent No-Retention Testing Mode
To allow testing and live demonstrations of the bot's full pipeline without modifying or polluting the database:
* **Toggles:** Toggled per-chat using the `/memory_off` and `/memory_on` Telegram commands.
* **Transaction Rollback:** When active, the bot processes all inputs normally, but overrides the underlying SQLAlchemy session commits (`NonRetentiveAsyncSession.commit()`) to bypass permanent serialization.
* **Persistent Chat IDs Set:** The set of chat IDs with memory turned off is serialized to `/data/no_retention_chats.json` adjacent to the SQL database, ensuring no-retention status survives restarts and process reboots without requiring any database schema alterations.
* **In-Memory Drafts:** Since database transactions are rolled back, standard database-based `PendingDraft` FSM envelopes would also be lost, breaking multi-turn clarification prompts. To keep multi-turn conversations working perfectly, an in-memory draft registry (`InMemoryPendingDraft`) safely handles and preserves active draft contexts for no-retention chats.

## What's deliberately not here yet

Free-text corrections of historical entries and automatic recalibration of the
activity factor are out of scope for now - see
`openspec/changes/archive/2026-08-16-calobot-v1/proposal.md` for why.
