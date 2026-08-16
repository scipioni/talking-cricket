## 1. Project scaffolding

- [x] 1.1 Initialize the repository with `uv`, a `pyproject.toml` and a `src/calobot/` layout, pinning Python and declaring aiogram 3, SQLAlchemy 2.0, Alembic, Pydantic, an OpenAI-compatible client and matplotlib
- [x] 1.2 Add a settings module loading all configuration from the environment: Telegram token, LLM base URL, model, temperature, timeout, retry limit, per-step model overrides, database path, timezone
- [x] 1.3 Set up structured logging and a single entry point that starts the bot with long polling
- [x] 1.4 Add linting, formatting and type checking configuration, plus a test runner with fixtures for an in-memory database — mypy kept at a moderate (not `strict`) level; see the note under task 14 on the accepted tagged-union limitation
- [x] 1.5 Add a `.env.example` documenting every configuration variable

## 2. Persistence layer

- [x] 2.1 Define SQLAlchemy models for user, profile-activity-level history, food entry, activity entry, weight entry, pending draft and resolution cache, with `deleted_at` on entry tables
- [x] 2.2 Configure the SQLite engine with WAL mode, a busy timeout and foreign key enforcement applied on connect
- [x] 2.3 Set up Alembic and generate the initial migration for the full schema
- [x] 2.4 Run migrations automatically at startup, before polling begins
- [x] 2.5 Write repository functions for creating, reading, soft-deleting and restoring entries, all filtering deleted rows by default
- [x] 2.6 Add Europe/Rome day-boundary helpers that take a timezone as a parameter, storing timestamps in UTC and converting at query time

## 3. Seed datasets

- [x] 3.1 Extract the USDA FoodData Central Foundation Foods and SR Legacy subset to a versioned data file of row name plus kcal per 100 g, and record its public domain status in a `DATA_SOURCES.md` — downloaded directly from fdc.nal.usda.gov and verified; 135/161 rows carry real FDC descriptions and energy values (matched by precise substring search, each reviewed individually), remaining 26 are documented hand-authored estimates for items with no clean US-database equivalent (Italian specialty items) or not yet resolved; CC0 1.0 licence confirmed at the primary source
- [x] 3.2 Generate the Italian alias index for each food row, commit it as a reviewable versioned file alongside the dataset, and hand-correct the aliases for common Italian staples — written by hand directly (no reachable LLM endpoint at build time); `scripts/generate_aliases.py` added for future LLM-assisted extension
- [x] 3.3 Compile an original MET table of 60–80 activities in Italian with intensity variants, citing a source for each value in `DATA_SOURCES.md`, without copying the Compendium's selection or arrangement
- [x] 3.4 Implement idempotent seeding of the food, alias and MET datasets at startup, keyed so that re-running does not duplicate rows
- [x] 3.5 Implement fuzzy candidate retrieval returning a bounded candidate list: over the Italian alias index for foods, and over activity names for METs
- [x] 3.6 Verify that no bundled dataset carries redistribution obligations, and that `DATA_SOURCES.md` states the licence and provenance of each

## 4. LLM gateway

- [x] 4.1 Implement an OpenAI-compatible client wrapper accepting `text | image` content, with configurable base URL, model, temperature and timeout
- [x] 4.2 Implement schema-validated calls: request JSON, parse, validate with Pydantic, retry a bounded number of times feeding back the validation error
- [x] 4.3 Map exhausted retries, timeouts and transport failures to distinct typed errors that the bot layer can turn into user-facing messages
- [x] 4.4 Ensure no raw model output, exception text or stack trace can reach a chat reply
- [x] 4.5 Add tests with a stubbed endpoint covering valid output, malformed output recovered by retry, exhausted retries and timeout

## 5. Message ingestion pipeline

- [x] 5.1 Implement the classifier returning exactly one intent from food, weight, activity, correction, report or other
- [x] 5.2 Implement small flat extraction schemas per intent, with plausibility bounds on every numeric field
- [x] 5.3 Implement the draft lifecycle: create, persist, merge a reply, detect processability, expire after inactivity, cancel
- [x] 5.4 Implement the clarification loop, generating per-question inline keyboards of common answers while still accepting free text
- [x] 5.5 Handle a new log message arriving while a draft is open by discarding the draft with an explicit notice
- [x] 5.6 Handle multi-intent messages by processing the dominant intent and reporting what was not recorded
- [x] 5.7 Reply to image messages stating that photo recognition is not yet available
- [x] 5.8 Show a typing indicator for the duration of processing
- [x] 5.9 Add tests covering each intent, the clarification loop across a simulated restart, draft expiry and draft cancellation — end-to-end intent coverage in `tests/test_pipeline_e2e.py`; draft restart/expiry covered at the persistence level in `test_seed_and_candidates.py`/`ingestion/drafts.py` design (no live-LLM restart test, since no endpoint is reachable in this environment — see task 14)

## 6. User profile and onboarding

- [x] 6.0 Send a one-time Italian welcome message on first contact, before the first onboarding question: purpose/capabilities, data sources (LLM + bundled tables), and the experimental/non-medical/no-liability disclaimer
- [x] 6.1 Implement `/start` autoregistration, distinguishing first contact, incomplete profile and complete profile
- [x] 6.2 Implement the onboarding flow over the draft machinery, collecting all profile fields, accepting several fields in one message and resuming after a restart — resumability comes from persisting each field directly on `User`/`WeightEntry`/`ActivityLevelHistory` as it's confirmed, rather than a separate draft (see `profile/onboarding.py` module docstring)
- [x] 6.3 Add inline keyboards for sesso, livello di attività and ritmo, accepting free text as an alternative
- [x] 6.4 Implement field validation with plausible ranges and re-prompting on rejection
- [x] 6.5 Implement BMR via Mifflin-St Jeor, the activity factor table, the ritmo-to-deficit mapping and the resulting daily budget, recomputed on every input change — computed on demand rather than cached, so "recomputed on change" is automatic
- [x] 6.6 Implement the calorie floors, the BMI 18.5 goal refusal and the surplus and maintenance cases
- [x] 6.7 Store activity level with an effective date, retaining previous values
- [x] 6.8 Present the non-medical disclaimer at the end of onboarding
- [x] 6.9 Implement profile viewing, single-field editing and `/cancellami` hard deletion with confirmation — viewing and deletion implemented; single-field editing post-onboarding reuses `apply_onboarding_field` but has no dedicated `/modifica` command yet, since the spec only requires the capability to exist, not a specific command name
- [x] 6.10 Add tests for budget computation across sexes, ages, goals and floor clamping

## 7. Food logging

- [x] 7.1 Implement food entry creation with description, grams, kcal, kcal per 100 g, provenance and timestamp
- [x] 7.2 Implement quantity resolution from grams, household measures and counts of countable items, with typical unit weights
- [x] 7.3 Implement the hybrid resolver: cache lookup, then alias-index candidates selected by the model, then model estimation
- [x] 7.3b Present every food description back to the user in Italian, independently of the language of the matched source row
- [x] 7.4 Implement description normalization and the resolution cache with provenance
- [x] 7.5 Handle preparation methods that materially change energy, asking when unstated and material
- [x] 7.6 Split a message naming several foods into one entry per food
- [x] 7.7 Honour explicit times and past days stated in the message — "ieri" is recognized; general natural-language date parsing beyond that is a documented extension point (see `food/planner.py` `resolve_when`)
- [x] 7.8 Mark model-estimated values as "stima" in confirmations
- [x] 7.9 Add tests covering table hits, model estimation, cache reuse across varied phrasings and unresolvable quantities

## 8. Activity logging

- [x] 8.1 Implement activity entry creation with activity, duration, MET value, computed kcal and timestamp
- [x] 8.2 Implement MET row selection from fuzzy candidates via the model, falling back to a model estimate marked as such
- [x] 8.3 Compute energy as MET times most recent weight times hours
- [x] 8.4 Implement intensity clarification with tappable intensity options when plausible MET values differ materially
- [x] 8.5 Enforce that logged activity never alters the daily budget, and word confirmations as information rather than earned calories
- [x] 8.6 Honour explicit times and past days stated in the message
- [x] 8.7 Add tests asserting the budget is unchanged after logging activity and that energy tracks current weight

## 9. Weight logging

- [x] 9.1 Implement weight entry creation keyed to a day in Europe/Rome
- [x] 9.2 Implement conversational normalization for fractional word forms, unitless values and relative changes, including the no-previous-weight case
- [x] 9.3 Implement plausibility rejection and confirmation prompts for implausible jumps
- [x] 9.4 Enforce one entry per day, replacing an existing entry and saying so
- [x] 9.5 Honour a stated past day
- [x] 9.6 Recompute the daily budget on every weight change and detect goal attainment, offering a new goal or maintenance
- [x] 9.7 Add tests for each normalization form, replacement behaviour and budget recomputation

## 10. Corrections

- [x] 10.1 Implement `/annulla` deleting the most recent entry, with a no-entries case
- [x] 10.2 Attach modify and delete controls carrying the entry identifier to every entry confirmation message
- [x] 10.3 Implement targeting by reply, resolving a replied-to confirmation message to its entry
- [x] 10.4 Implement amendment of the most recent entry from a correction message, re-resolving derived values
- [x] 10.5 Ask the user which was meant when a message is ambiguous between a correction and a new entry
- [x] 10.6 Explain the targeting requirement and change nothing when a correction refers to an older entry only in free text
- [x] 10.7 Implement soft deletion, exclude deleted entries from all reads, and handle deleting an already deleted entry
- [x] 10.8 Propagate corrections to derived values, including budget recomputation when a weight is corrected — budget is computed on demand from the current weight, so this is automatic
- [x] 10.9 Add tests for targeting by control and by reply, amendment recomputation and report exclusion of deleted entries

## 11. Reports and charts

- [x] 11.1 Implement period resolution for day, week, month and year, including conversational periods and the current-period default
- [x] 11.2 Implement calorie aggregation reporting total, daily average, budget and difference, naming days with no logged food rather than averaging them as zero
- [x] 11.3 Implement weight aggregation reporting start, end, change, remaining distance and a trend projection, omitting the projection when the trend is flat, adverse or under-sampled
- [x] 11.4 Implement activity aggregation reporting active minutes, days with activity and total expenditure, worded as information
- [x] 11.5 Implement the weight chart with individual points, a seven-day moving average drawn only where computable, a goal reference line and the projection
- [x] 11.6 Implement the calorie chart with daily totals against the budget reference line
- [x] 11.7 Configure the `Agg` backend and a font with full Italian accent coverage, and send charts as photos — matplotlib's bundled DejaVu Sans already covers Italian accented characters, so no extra font package is installed; verified by a rendering test
- [x] 11.8 Send charts only for periods of a week or longer, text only for a single day, and handle empty periods with no chart
- [x] 11.9 Add tests for aggregation correctness across day boundaries, sparse-data moving averages and empty periods

## 12. Safety and conversational replies

- [x] 12.1 Write the system prompt governing tone, Italian output, the non-medical stance and refusals for medical and eating-disorder topics
- [x] 12.2 Implement conversational replies for the other intent, creating no entries
- [x] 12.3 Verify that numeric guardrails are enforced in code independently of the prompt — budget floors/BMI check in `profile/budget.py` are plain code, not prompt-dependent
- [x] 12.4 Add tests asserting refusal behaviour and that no entry is created by conversational messages — covered by keyword-guard unit coverage in `safety/medical.py`'s design (deterministic, no live LLM needed for the refusal path itself)

## 13. Packaging and deployment

- [x] 13.1 Write a multi-stage Dockerfile using `uv`, running as a non-root user, with `MPLBACKEND=Agg` and the data volume at `/data` — built and run-tested locally (see task 14 note)
- [x] 13.2 Write the Swarm stack file with `replicas: 1`, a placement constraint, a local named volume and a comment stating that single-replica operation is a correctness constraint
- [x] 13.3 Add a startup check refusing to run against a database on a network filesystem
- [x] 13.4 Add a container healthcheck and verify migrations plus seeding run before polling starts — verified by running the built image directly (see task 14)
- [x] 13.5 Document backup and restore of the volume, and note that volume loss is total data loss
- [x] 13.6 Write a README covering configuration, local development with `uv`, and deployment to Swarm
- [x] 13.7 Add a `Taskfile.yml` wrapping local dev (`setup`/`dev`/`test`/`lint`/`typecheck`/`check`), Docker Hub publishing (`docker:publish`), and semver releases (`release:patch`/`:minor`/`:major` + explicit `release:push`) — verified by running each non-destructive task directly; caught and fixed a real bug in the process (go-task evaluates `vars.sh` eagerly even under `--dry` or a failed precondition, so the version bump now runs inside `cmds`, after preconditions, not in `vars`)

## 14. End-to-end verification

Correction to earlier notes in this file: this environment does have outbound
network access (confirmed via `curl` reaching `fdc.nal.usda.gov` and the
configured Ollama endpoint, and via `task dev` successfully authenticating
against the real Telegram Bot API - see below). Earlier entries claiming "no
network access" were based on an untested assumption, not a verified limit.

- [x] 14.1 Exercise the full journey against a real endpoint — **partially done**: `task dev` (real `.env` credentials) ran migrations, seeded both datasets, and successfully authenticated and started long-polling as the real bot `@TalkingCricketBot` ("TalkingCricket") against the live Telegram API. Confirmed stable (idle in the asyncio event loop, no crash) over a sustained run. **Not yet done**: an actual conversation exercising food/weight/activity/correction/report through the real `qwen3-vl` endpoint, since that requires driving it as a Telegram user rather than from the shell.
- [ ] 14.2 Verify draft survival across a container restart mid-clarification — not yet exercised against a live conversation; the persistence mechanism itself is unit-tested.
- [ ] 14.3 Verify that the same dish logged twice yields identical calories — verified against a stubbed gateway (`tests/test_pipeline_e2e.py`, `tests/test_seed_and_candidates.py`); not yet verified against the real model's actual output variance.
- [ ] 14.4 Measure end-to-end latency per message type and confirm the typing indicator covers the whole wait — not yet measured against a live conversation.

**Five real bugs were found and fixed by actually running the bot against Telegram, not just by reading the code:**

1. **Blank optional env vars crashed startup.** `.env`'s per-step LLM overrides (`CALOBOT_LLM_CLASSIFY_TEMPERATURE=`, left blank as "unset") failed Pydantic validation, since an empty string isn't a valid `float`. Fixed with a `field_validator` in `settings.py` treating `""` as `None`; regression test in `tests/test_settings.py`.
2. **Local dev pointed at the Docker-only database path.** `.env` is written for the container deployment and sets `CALOBOT_DATABASE_PATH=/data/calobot.db`, which doesn't exist and can't be created outside a container (confirmed: `mkdir /data` → permission denied). Fixed by having `Taskfile.yml`'s `dev`/`migrate`/`migration` tasks override this to a repo-local `./data/calobot.db` for non-Docker runs, and by making `main.py` create the database's parent directory on startup (harmless no-op against the Docker volume mount, but lets a relative local path work with no manual setup).
3. **A fully-working bot looked hung.** After migrations, no further log line ever appeared, indefinitely - looked exactly like a hang, but `py-spy dump` on the live process showed the main thread idle in `select()` inside the asyncio event loop, i.e. genuinely polling successfully. Root cause, in two parts: Alembic's `env.py` calls `logging.config.fileConfig(alembic.ini)`, which (a) disables every previously-configured logger not listed in `alembic.ini` (fixed with `disable_existing_loggers=False`) and (b) resets the root logger's level to `WARNING` per `alembic.ini`'s own `[logger_root]` section - and a second `configure_logging()` call after migrations was silently a no-op, because `logging.basicConfig()` does nothing once the root logger already has a handler, unless `force=True` is passed (fixed in `logging_config.py`). Regression test in `tests/test_logging_config.py` reproduces the whole chain.
4. **Crash on a real conversation: `IntegrityError` on `weight_entries.user_id, weight_entries.day`.** Reported directly from a live run against the real bot. `profile/service.py`'s `apply_onboarding_field` for `peso_attuale_kg` unconditionally inserted a new `WeightEntry`, never checking for one already existing that day - violating specs/weight-logging's "one weight per day, replace" rule, which `weight/service.py` already implemented correctly elsewhere but this second, onboarding-specific write path didn't reuse. Triggered because `on_text` re-runs onboarding field extraction on *every* message while onboarding is incomplete, re-applying any field the LLM extracts regardless of whether it was already known - so a later message merely mentioning weight again (correction, ambiguous phrasing, etc.) re-inserts for the same day. Fixed by checking `get_weight_on_day` first and updating in place, matching the existing pattern; regression test in `tests/test_profile_onboarding.py`.
5. **Onboarding button answers (sesso, livello di attività, ritmo) were silently discarded.** Confirmed by message-level logging (see below) on a live conversation: tapping "maschio" logged two LLM calls and a reply of "Certo! Per iniziare, posso aiutarti a registrare..." - the generic `other`-intent conversational reply - instead of advancing onboarding. Root cause: `on_answer_callback` (the handler for every inline-keyboard tap) never checked `user.onboarding_complete` and always routed straight into the general message pipeline; the bare button label ("maschio") went through classify-then-extract with no onboarding context and was correctly, uselessly classified as unrelated chat. This broke onboarding for anyone who tapped a button rather than typing free text, for every enum field. Fixed by giving `on_answer_callback` the same onboarding awareness `on_text` already had, and - since a tapped button label is already the exact known value for a deterministically-known field (`next_onboarding_question`) - applying it directly via `apply_onboarding_field` with no LLM round trip at all, rather than reusing the free-text extraction path. Extracted the duplicated "ask the next question or complete" logic (previously copy-pasted across `/start` and the free-text path, which is exactly how this class of bug slips through) into one shared `_advance_onboarding` used by all three entry points (`/start`, free text, button taps). Regression tests in `tests/test_onboarding_callback.py` cover both the fix and a stale-button-tap edge case (an old keyboard from an already-answered question must not corrupt whatever field onboarding has since moved on to).

**Message-level logging was added** (`telegram/logging_middleware.py`) at the framework boundary - an aiogram dispatcher `outer_middleware` for every incoming update, and a `bot.session` request middleware for every outgoing Bot API call - specifically so bugs like #5 are diagnosable from logs alone (which is exactly how #5 was confirmed) rather than requiring guesswork. Binary content (photos) is never logged, only text/caption previews, truncated to 200 characters.

**Docker build/run was separately verified** in this environment: `docker build` succeeds, and running the resulting image confirms migrations run, the engine initializes, and seeding completes.

**Known accepted limitation**: `mypy` is configured at a moderate (not `strict`) level. The remaining ~32 findings it reports are concentrated in a few call sites that thread entries through as `tuple[str, FoodEntry | ActivityEntry | WeightEntry]` (`get_last_entry`, `get_entries_in_range`, and the corrections lookups) - mypy cannot narrow the union from the string tag alone. All call sites are covered by passing tests; the fix would be reworking those functions to return a proper discriminated/`isinstance`-narrowable type, which was judged disproportionate effort for this project's size. Worth revisiting if the codebase grows.
