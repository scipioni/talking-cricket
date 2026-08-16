## Context

Greenfield repository — nothing exists yet beyond the OpenSpec scaffold. See `proposal.md` — Why for motivation, and the seven specs under `specs/` for the behaviour being built.

Three constraints shape almost every decision below:

- **The language model is small and self-hosted.** `qwen3-vl:30b-a3b-instruct` behind an Ollama OpenAI-compatible endpoint has roughly 3B active parameters. It is fast and free of token limits, but schema adherence is model-enforced rather than grammar-enforced, and it degrades on large nested schemas. Every design choice that touches the model favours *many small prompts* over *one clever prompt*.
- **SQLite with exactly one writer.** The deployment target is Docker Swarm, whose purpose is scheduling replicas across nodes; SQLite's is a single file with a single writer. These are in direct tension and the resolution has to be explicit and enforced, not assumed.
- **Users write messily and expect the bot to cope.** The entire value proposition is the absence of forms, so the interpretation layer must be tolerant, and everything downstream of it must assume the interpretation might be wrong.

## Goals / Non-Goals

**Goals:**

- An interpretation pipeline that stays reliable on a small local model, and degrades into a plain "non ho capito" rather than into wrong data.
- Reproducible calorie figures: the same food logged twice yields the same number, so a trend reflects behaviour and not model variance.
- A schema and interface shape that admits image input and historical corrections later without restructuring.
- Operational honesty: the single-writer constraint is enforced by the stack file, not left to whoever scales the service next.

**Non-Goals:**

- Multi-node or multi-replica operation. Explicitly designed against.
- Nutrient tracking beyond energy (macros, micronutrients). The data model should not preclude it, but nothing in v1 computes it.
- A general nutrition chat assistant. Conversational replies exist, but the product is a logger.
- Provider-agnostic abstraction over language models beyond an OpenAI-compatible surface.

## Decisions

### Stack

**Python with `uv` and a `src/` layout, `aiogram 3` for the bot.** aiogram is async-native, has first-class FSM and callback-query handling, and its router model fits the classify-then-dispatch shape directly. python-telegram-bot would also work; aiogram's inline-keyboard and FSM ergonomics are the deciding factor given how central buttons and drafts are here.

**SQLAlchemy 2.0 + Alembic, not SQLModel.** SQLModel is more pleasant to write, but its Alembic integration is rough exactly where this project needs migrations to be boring. The user asked for "best and simple"; those pull apart here, and reliable migrations win over terser model definitions.

**Long polling, not webhooks, for v1.** Webhooks need a public TLS endpoint and turn the bot into an inbound service; long polling works behind whatever Swarm's ingress happens to be and has no such requirement. With one replica there is no polling conflict. Webhooks remain a configuration-level change later.

### Persistence

**SQLite in WAL mode, single replica, pinned volume.** The stack file must set `replicas: 1`, a placement constraint binding the service to one node, and a named local volume mounted at `/data`. A network filesystem is explicitly rejected: SQLite's locking is unreliable over NFS and the failure mode is silent corruption. WAL mode is set at startup, along with a busy timeout, so that the reporting queries do not block ingestion.

The single-replica constraint is a correctness requirement, not a capacity choice, and belongs in a comment in the stack file saying so.

**Alembic from the first commit**, with the initial schema as a migration rather than `create_all`. There is no "later" moment at which retrofitting migrations is cheaper.

**Soft deletes via `deleted_at`.** Every report query filters on it. Append-only versioning with a `superseded_by` chain was considered and rejected: it buys the ability to audit the model's mistakes over time, at the cost of complicating every aggregate query. If model quality auditing becomes interesting, the resolution cache already records provenance and is the better place to look.

### The interpretation pipeline

**Classify, then extract, in two calls.** One call returning a union of five event types is the design a large model would prefer; this model does noticeably better with a tiny classification prompt followed by a small, flat, intent-specific extraction schema. There are no token limits to economise against, so the second round trip costs only latency.

The classifier returns a single intent and nothing else. Multi-intent messages are handled by processing the dominant intent and telling the user what was ignored — attempting to split a message into several events is a v2 problem and a reliable source of wrong data if attempted with this model now.

**Pydantic validation with bounded retry, feeding the validation error back.** The model will occasionally emit schema-shaped but semantically wrong output — a quantity as a free-text string, an invented enum value. Validation failures retry twice with the error text appended; exhaustion produces a user-facing "puoi riscrivere?" and no stored data. No raw model output, exception text or stack trace ever reaches the chat.

**Schemas stay small and flat.** Nesting and unions are where this model's adherence falls off. Where a nested structure seems natural, prefer a second call.

**Per-step model configuration.** Base URL, model, temperature, timeout and retry count are environment-driven, and the model is overridable per pipeline step, so classification can later run on something smaller and faster than extraction without a code change.

**The extraction interface takes `text | image` from day one**, even though v1 answers images with "non ancora supportato". The configured model is vision-capable, so photo logging is the obvious next feature; making the content type a union now costs one type definition and avoids threading an image through the whole pipeline later.

### Drafts and the clarification loop

**Drafts live in the database, not in aiogram's FSM memory storage.** The volume and the schema already exist, a Swarm restart mid-conversation is a normal event, and a persisted draft is inspectable when the pipeline misbehaves. A `pending_draft` row holds the intent, the partial payload, the field currently being asked for, and a timestamp for expiry.

**Ask rather than assume, but always offer buttons.** The chosen policy is to keep asking until the draft is processable — no silent default portions. The interrogation risk this creates is mitigated entirely in the presentation layer: every clarification offers the common answers as inline keyboard buttons (`[piccolo ~80g] [medio ~120g] [abbondante ~180g]`), so the usual case is one tap, and free text is always accepted as an alternative. Buttons are generated per question, not fixed.

A new log message arriving while a draft is open discards the draft with an explicit notice, rather than queueing or silently dropping it.

### Calorie resolution

**Cache → table → model, with the model as a matcher rather than a search engine.** Candidate rows are retrieved from the bundled food table by cheap fuzzy name matching, and the model chooses among them or declares that none fits. This inverts the usual difficulty: retrieval can be sloppy because disambiguation is the model's job, and it avoids building embedding search or a serious fuzzy-matching stack.

**A bundled food composition table, not a live API — and the source is chosen by licence first.** Shipping the data in the image means no network at first boot, no rate limits, nothing to host, and a dataset that cannot change under the application's feet. That is only viable with a source that permits redistribution, which rules out the obvious candidate:

- **CREA** has the best Italian coverage and the worst legal position: no open licence, and in the EU the compilation carries the *sui generis* database right independently of copyright. Rejected.
- **OpenFoodFacts** is ODbL — genuinely open, but share-alike is triggered by *publicly using* a derived database, not merely distributing it, so bundling a derived table would attach obligations to the service itself. Kept out of the bundled path; it remains the natural runtime source for barcode lookups later, where an attribution line satisfies ODbL cleanly.
- **USDA FoodData Central** is a US government work in the public domain, with no obligations whatsoever, and is high quality. Chosen — the *Foundation Foods* / *SR Legacy* subset rather than the full dump, so a few thousand curated rows rather than hundreds of thousands of branded products.

**The LLM erases USDA's one drawback.** English, US-centric row names would be fatal for string matching, but matching is not what the model does here — it *selects* among retrieved candidates, and choosing "Nuts, walnuts, english" for **"noci"** is a translation task, which is what language models are best at. Retrieval still needs Italian, so an **Italian alias index is generated once at seed time** by translating each row name, stored alongside the row, and used for fuzzy candidate retrieval. Translating the query at each cache miss was the alternative; the seed-time index is paid once, is inspectable, and gives a natural place to hand-correct the names that matter.

What genuinely falls through are Italian-specific foods — stracchino, bresaola, taralli. These take the LLM estimation path, which is the fallback already accepted, and are precisely the foods a language model knows well.

**The resolution cache is what makes the product trustworthy.** Keyed on a normalized description, storing kcal per 100 g and provenance (`table` or `llm`), it guarantees that "pasta al pesto" costs the same on Friday as on Tuesday. Without it the same dish would drift between entries and the weekly totals would be noise. Provenance is surfaced to the user as "stima" where relevant, and gives a later feature a way to upgrade estimates to table values.

**Activities get the same structure but with real physics behind them**: `kcal = MET × peso × ore`, MET row selected by the model from fuzzy-retrieved candidates of a bundled table. The coupling to current weight is deliberate — it is one of the places the three tracked quantities reinforce each other.

**The MET table is compiled in-house rather than taken from the Compendium of Physical Activities.** The Compendium's licensing is unclear for this use, and copying it wholesale would copy the protected part: a MET value is a fact and facts are not copyrightable, but the Compendium's selection, arrangement and 800-row taxonomy are. So the bundled table is an original compilation of 60–80 activities that users of an Italian weight-tracking bot actually report, written in Italian, with values sourced and verified individually. This is not only the safe option but the better one — fewer, more relevant candidates improve the model's row selection, where 800 rows including "churning butter, manual" would degrade it. Anything outside the table takes the LLM estimation path.

### Energy model

**Energy model B: the budget comes from `BMR(Mifflin-St Jeor) × fattore_attività − deficit(ritmo)`, and logged activity never moves it.** The activity factor in the profile already accounts for habitual movement; adding logged activity on top would double-count it, which is the most common defect in this category of application.

The consequence is that activity logging must earn its place through reports rather than through the budget, and that the bot's wording matters: confirmations say *"registrato: camminata 30 min, ~150 kcal"*, never *"hai guadagnato 150 kcal"*. This is a normative requirement in `specs/activity-logging`, not a style preference, because the model will otherwise invent the encouraging phrasing on its own.

A second consequence is that a stale activity factor silently corrupts the budget. Hence the profile stores activity level with an effective date and retains history, so that automatic recalibration — comparing predicted against actual weight change — can be added later without a migration of meaning.

### Reports and charts

**matplotlib rendering to PNG, sent as a photo.** Charts are worth their cost here: a year of raw weight numbers is unreadable, and a trend line is the single most motivating output the bot produces. The cost is real — roughly 60 MB in the image plus a font with proper accent coverage — and is paid deliberately in a multi-stage build with `MPLBACKEND=Agg`.

**A seven-day moving average on the weight chart is non-negotiable.** Daily weight swings by up to a kilogram from water and salt; showing raw points alone makes users read noise as failure. The average is drawn only where enough points exist rather than interpolating across gaps, so sparse logging looks sparse instead of looking smooth.

**Days with no logged food are named, not averaged as zero.** A forgotten day would otherwise drag the weekly average down and make the report actively misleading.

### Safety

Guardrails live in two places, because the model cannot be trusted to enforce them alone: **validation code** clamps the budget to the floor (1500 kcal M / 1200 kcal F) and refuses goals implying BMI < 18.5, while the **system prompt** governs tone and refusals for medical and eating-disorder topics. Code enforces the numbers; the prompt handles the conversation.

Health data lives in one SQLite file, so `/cancellami` performs a hard delete of the user and all their rows — the only place soft-deletion does not apply.

### Timezone

`Europe/Rome` is a configuration constant applied at every day boundary, with UTC timestamps stored in the database and converted at query time. Per-user timezones are not modelled; adding them later means a nullable column and a lookup, which the day-boundary logic should be written to accommodate by taking the timezone as a parameter rather than reading the constant directly.

## Risks / Trade-offs

- **Small model produces confidently wrong extractions** (e.g. 100 g read as 1000 g) → Plausibility bounds on every extracted number, confirmation messages that always restate what was understood, and one-tap correction controls on every confirmation. The user is the last line of validation and the interface must make correcting cheap.
- **Calorie estimates for composite dishes are approximate** → Accepted explicitly; provenance is stored and shown as "stima". The product promises a consistent trend, not clinical accuracy, and the cache guarantees the consistency part.
- **Someone scales the service to two replicas and the database diverges silently** → `replicas: 1`, a placement constraint, a local-only volume, and a comment in the stack file stating that this is a correctness constraint. A startup check that refuses to run against a database on a network filesystem is worth considering.
- **Ollama endpoint unavailable or slow** → Bounded timeout, typing indicator during processing, explicit "servizio non disponibile" reply, and nothing stored on failure. The bot never hangs silently.
- **Clarification loop becomes an interrogation and users disengage** → Buttons on every question, and clarification limited to fields that genuinely change the result. This is the design's largest usability bet and is the first thing to re-examine after real use.
- **matplotlib inflates the image and slows cold starts** → Multi-stage build, `Agg` backend, no interactive dependencies. If it proves too heavy, server-side chart rendering is replaceable behind the report interface.
- **Single SQLite file holds all users' health data** → Volume backups need to exist from day one; a corrupt or lost volume is total data loss. Backup is an operational task, not an application feature, but it must not be skipped.
- **Italian-specific foods are absent from a US dataset** → They fall through to LLM estimation and are cached, so they stay consistent even though they are estimated. If a category proves important, the alias index is the place to add hand-written rows.
- **Seed-time alias translation is a one-off LLM cost with no human review** → The alias index is a committed, inspectable artifact rather than a runtime side effect, so a bad translation is a data fix rather than a debugging session.
- **Italian-only prompts and datasets** → Accepted for v1. The prompt layer should keep user-facing strings separable enough that a second language is a translation job rather than a rewrite.

## Migration Plan

No migration — greenfield. Deployment is a fresh Swarm stack: create the volume, deploy with one replica, run Alembic migrations on startup before the bot begins polling, and seed the food and MET tables idempotently on first run. Rollback is redeploying the previous image tag; since migrations run forward on start, any schema change needs a working downgrade path before it ships.

## Open Questions

- Whether the alias index is better generated by the language model at seed time or written by hand for the few hundred foods that matter most. The design assumes generated-then-correctable; real usage will show whether correction is frequent enough to invert that.
- Whether classification and extraction should eventually use different models. The configuration supports it; whether it helps is an empirical question to answer after measuring real messages.
- Whether Ollama's OpenAI-compatible layer enforces `response_format: json_schema` strictly enough to relax the retry logic. The retry path is needed regardless, so this only affects how often it fires.
