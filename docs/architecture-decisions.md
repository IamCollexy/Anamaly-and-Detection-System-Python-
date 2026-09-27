# Architecture decisions: reading this repository as a backend engineer

This is a code-first map of the current repository, not a target-state design. The application is an early CSV-focused slice: it has FastAPI routes, SQLAlchemy models, CSV ingestion, Celery tasks, and an OpenAI adapter. It does **not** yet have middleware, a task-status API, Excel/JSON routes, an actual Redis cache, database integration tests, or a deployed/verified Compose run. Where the code does not establish a behavior, this document says so.

# Technology: FastAPI

## Problem

The system needs a public HTTP boundary for uploads, job lookup, reconciliation requests, findings, and health checks. Those operations need input extraction, lifecycle-scoped database access, HTTP status semantics, and a stable response contract; a pile of ad-hoc WSGI handlers would make these concerns easy to mix with domain work.

## Why it exists here

`app/main.py` owns all current routing: `POST /imports` saves an upload and returns `202`, `GET /imports/{job_id}` returns a job, `POST /reconciliations` publishes work, and `/findings` pages results. `Depends(get_session)` injects the generator dependency from `app/database.py`; the `finally` closes the SQLAlchemy session after the request. `ImportCreated`, `JobRead`, and `FindingRead` are declared response models. `HTTPException` expresses unsupported file type, absent job/finding, and an integrity race as HTTP failures. All current routes are synchronous `def` routes; the async OpenAI call happens inside a Celery worker through `asyncio.run`, not in FastAPI. **Current limitation:** no middleware is registered, so there is no request-ID, structured request log, authentication, CORS policy, or central exception handler despite the earlier project intent.

## What happens without it?

Current: `client → FastAPI route + dependency → database/job publication → response`.

Without it: `client → custom HTTP framework/handler → database/job publication → custom serialization`. The queue and domain code could remain, but response validation, OpenAPI/docs, dependency lifecycle, and clear HTTP exceptions would need manual replacements. A plain script is simpler only if there is no HTTP API.

## Alternatives

* **Django + Django REST Framework:** solves routing, ORM, admin, and validation; it is heavier and duplicates this repository's SQLAlchemy-oriented learning goal.
* **Flask:** a minimal Python web layer, closer to Express ergonomics; the repository would need extensions or conventions for request parsing, OpenAPI, and DI lifecycle.
* **Starlette:** FastAPI's lower-level foundation; suitable when automatic schema generation/Pydantic integration is not wanted, but more plumbing here.
* **NestJS/Express/Fastify:** valid if the team remains in TypeScript; it would not teach the Python runtime and ecosystem this project is designed to expose.

## Why this project chose it

* **Technical reason:** route signatures can declare validated/injected inputs and response models next to endpoint behavior.
* **Ecosystem reason:** it naturally pairs with Pydantic and ASGI tooling already listed in `pyproject.toml`.
* **Learning reason:** it makes Python's generator dependencies and sync/async route choices visible rather than hiding them behind a Nest module system.

Tradeoff: it is not “Python Express.” Its route parameter inspection and Pydantic serialization are opinionated, and mixing blocking work into async handlers would still be a bug.

## When I would NOT use it

Do not add FastAPI to a one-off CSV repair script, a pure worker, or a service where an existing Django application already provides the correct boundary. For a very small internal webhook handler, Flask may reduce dependency surface. Do not choose FastAPI merely because handlers can be `async`; a blocking pandas import does not become non-blocking just by changing `def` to `async def`.

## Failure modes

* Missing `Idempotency-Key` is rejected by FastAPI header validation before route execution.
* Non-CSV file names receive `415`; content is not inspected, so a `.csv` with invalid rows reaches worker parsing.
* A concurrent unique-key conflict is mapped to `409` after rollback in `create_import`.
* A database failure in `/ready` or any route currently bubbles as an uncustomized server error. **Current limitation:** no global error middleware/handler or request tracing exists.
* `import_file.delay` can fail after the job commit; the job remains queued, but no recovery publisher/outbox exists. **Current limitation.**

## Node.js / TypeScript analogy

FastAPI routes plus `Depends(get_session)` are closest to a Nest controller whose handler receives a scoped provider. Similarity: both keep transport extraction out of service code. Difference: FastAPI invokes a Python callable and treats its `yield`/`finally` as lifecycle cleanup; it is not a DI container that constructs decorated classes. Conceptually, `def ready(session=Depends(get_session))` is closer to “inject request-scoped database session into this handler” than to `@Injectable()` registration.

## Python concepts I should learn from this technology

Type annotations on parameters/returns; decorators (`@app.get`, `@app.post`); generator dependencies; context cleanup with `try/finally`; keyword arguments/defaults; synchronous versus coroutine route functions; exceptions; Pydantic response models.

## Debugging questions

1. Did the request reach the intended route and pass FastAPI's input extraction?
2. Is the failure before the session dependency, inside the route, or while serializing the response?
3. Is this route doing only short request work, or accidentally doing worker work?
4. Which HTTP status is actually returned for the failure?

## Break-the-system exercise

### Experiment
Temporarily replace `Depends(get_session)` on `/ready` with a manually constructed `SessionLocal()` and omit closing it.

### Expected observation
Repeated readiness calls may leave sessions/connections unmanaged; compare the code's ownership clarity with the generator dependency.

### Questions to answer
1. Where does the normal session close? 2. Does `/ready` commit anything? 3. Who owns rollback on a route exception? 4. Why is manual lifecycle code risky under load?

### What to investigate next
Read `app/main.py`, `app/database.py`, and the FastAPI section of `docs/node-to-python.md`.

---

# Technology: Pydantic

## Problem

Python type hints communicate intent to humans and tools but do not stop a CSV value like `"oops"` from reaching persistence. The system has two untrusted boundaries: provider transaction records and LLM-generated explanation content. Both need parsing, normalization, and a known serialization shape.

## Why it exists here

`TransactionInput` in `app/schemas.py` parses provider data with `model_validate` in `normalize_record` (`app/services.py`), converts `amount` to `Decimal`, requires fields, creates isolated metadata dictionaries, and uppercases currency. Route response models (`ImportCreated`, `JobRead`, `FindingRead`) provide serialization contracts. `InvestigationExplanation` is the explicit AI boundary: `app/ai.py` passes it to the OpenAI SDK parse call, then `FindingRead` uses the same schema when serializing stored AI data. `model_dump` transforms validated transaction and AI objects before ORM/database use.

## What happens without it?

Current: `CSV dict/LLM response → Pydantic parse → normalized typed object → ORM/response`.

Without it: `untyped dict → manual casts/if statements → ORM` and `unvalidated AI dict → JSON column`. Validation becomes duplicated among routes, import code, and persistence; type hints would not protect runtime. The current worker catches bad row exceptions, but without Pydantic it would be much easier to store malformed values silently.

## Alternatives

* **Manual validation/dataclasses:** lightweight for a fixed private input; grows repetitive and has no equivalent model parsing/JSON schema behavior here.
* **msgspec:** high-performance parsing/serialization; a realistic choice for very high throughput, with a smaller learning/compatibility fit for FastAPI's Pydantic-first examples.
* **Marshmallow:** schema validation/serialization; works, but is a separate model style from modern FastAPI conventions.
* **TypeScript Zod/class-validator:** conceptual Node counterpart; only applies if the service is rewritten in Node.

## Why this project chose it

* **Technical reason:** the same model represents validation, parsing, and safe response/AI boundaries.
* **Ecosystem reason:** FastAPI and the OpenAI structured parsing API integrate directly with Pydantic models.
* **Learning reason:** this distinguishes static annotations from runtime validation for a TypeScript engineer.

Tradeoff: Pydantic does work per record. For massive controlled data pipelines, manually optimized parsing or columnar validation may be necessary.

## When I would NOT use it

Do not create a Pydantic model for every internal two-line helper or every ORM-to-ORM operation. A tiny private function may need ordinary types and a dataclass only. Do not rely on Pydantic to enforce database uniqueness, authorization, or cross-process consistency; those remain database/application responsibilities.

## Failure modes

* Missing/invalid row fields cause `model_validate` to raise; `ingest_csv` counts the row as rejected and continues.
* `pd.notna` removes missing values before parsing, so a required missing field becomes a validation failure instead of a database null.
* `FindingRead` expects `ai_explanation` to parse as `InvestigationExplanation`; legacy/corrupt JSON can fail response serialization. **Current limitation:** no migration/backfill or API error strategy exists for malformed stored AI JSON.
* A correct Pydantic model cannot ensure source CSV headers exist before `drop_duplicates`; a missing `provider`/`external_reference` column fails earlier. **Current limitation:** this likely fails the whole task rather than producing a clear file-level error.

## Node.js / TypeScript analogy

This is closest to a Nest DTO plus Zod/class-validator runtime parsing. Similarity: `TransactionInput` is a contract that transforms/rejects runtime data. Difference: a Python annotation such as `amount: Decimal` becomes runtime behavior only because Pydantic reads it; ordinary Python annotations are not equivalent to Zod. `model_validate(record)` is conceptually `transactionSchema.parse(record)`, then `model_dump()` is a controlled serialization step.

## Python concepts I should learn from this technology

Classes; type hints and unions (`str | None`); `@classmethod`; decorators/field validators; `Field`; `default_factory`; `Decimal`; model parsing and serialization; exceptions.

## Debugging questions

1. Is input being validated at the boundary before an ORM object is built?
2. Did parsing coerce a value (for example amount/currency) as intended?
3. Is the problem a Pydantic validation error or a later database constraint error?
4. Is stored JSON still compatible with the response schema?

## Break-the-system exercise

### Experiment
Temporarily remove the `currency` validator from `TransactionInput`, import equivalent `ngn` and `NGN` rows, then inspect stored values/findings.

### Expected observation
Look for whether a seemingly presentation-only normalization rule affects downstream grouping and consistency.

### Questions to answer
1. Which boundary owned normalization? 2. Does the database constraint prevent case inconsistency? 3. Would a SQL `UPPER()` alternative be better? 4. Which clients would see changed output?

### What to investigate next
Read `app/schemas.py`, `normalize_record`, and `docs/python-learning-map.md`.

---

# Technology: SQLAlchemy

## Problem

The application needs to translate Python objects into durable relational records, manage connections and transaction boundaries, query jobs/findings, and express relationships without manually concatenating SQL in every route/task.

## Why it exists here

`app/database.py` creates an `Engine` from `FINOPS_DATABASE_URL` with `pool_pre_ping=True`, a `sessionmaker`, and a declarative `Base`. `app/models.py` maps `ImportJob`, `Transaction`, and `Finding` using `Mapped`/`mapped_column`, including relationships. `get_session` gives routes a session. In `ingest_csv`, `session.begin_nested()` creates a SAVEPOINT around each row and `flush()` exposes a uniqueness failure before accepting it. Worker code explicitly commits job state. Query examples include `session.get`, ORM `query(...).filter_by`, `select(Transaction)`, and paginated finding query construction.

## What happens without it?

Current: `route/task → Session unit of work → Engine pool → PostgreSQL/SQLite`.

Without it: `route/task → handwritten SQL + driver connection management → database`. That can be appropriate, but this project would need to hand-build model hydration, relation queries, transaction lifecycle, and per-dialect behavior. Removing only the ORM while retaining SQLAlchemy Core is a plausible middle path.

## Alternatives

* **SQLAlchemy Core + psycopg:** explicit SQL and fewer ORM abstractions; ideal when query shape dominates, but more mapping code.
* **Django ORM:** integrated ORM if Django is the HTTP framework; less aligned with this FastAPI project.
* **Tortoise ORM / Piccolo:** async-first ORM alternatives; change the learning focus and maturity/query tradeoffs.
* **Prisma/TypeORM:** closest Node territory; their generated-client/decorator patterns are not how this repository's Python `Session` works.

## Why this project chose it

* **Technical reason:** maps relationships and constraints while retaining `select` and explicit session/transaction control.
* **Ecosystem reason:** SQLAlchemy 2 is broadly supported with PostgreSQL, Alembic, and Python tooling.
* **Learning reason:** it exposes unit-of-work semantics, rather than suggesting all persistence is a repository method call.

Tradeoff: ORM identity maps and implicit flush behavior need deliberate understanding; it can hide expensive query patterns if used casually.

## When I would NOT use it

Do not use a full ORM for a single reporting script with two stable SQL statements, a warehouse-heavy query workload where SQL is the product, or a high-volume bulk loader where `COPY`/driver-specific bulk ingestion is superior. Do not add a repository layer merely to hide every `Session`; this repository currently avoids that abstraction.

## Failure modes

* DB connection failure occurs when engine/session work is attempted; `pool_pre_ping` reduces stale pooled connection reuse but does not make the database available.
* Per-row unique failures are isolated by SAVEPOINT and counted rejected; other exceptions are also swallowed per row, which can hide systemic parsing/persistence defects. **Current limitation:** rejected-row reasons are not recorded.
* Worker job transitions commit separately from ingestion; a crash can leave `processing` or partial transaction state. **Current limitation:** there is no lease/reaper/state transition recovery.
* `reconcile` loads all transactions with `.all()`, exposing N+1 is not the immediate issue, but memory/query scale is. **Current limitation:** no eager-load strategy is needed today, but no scalable query strategy exists at large volume.

## Node.js / TypeScript analogy

SQLAlchemy occupies TypeORM/Prisma territory: models map data and a session performs persistence/query work. Difference: `Session` is an identity map and explicit unit of work; `session.add()` does not necessarily issue SQL until `flush()`/`commit()`. `with session.begin_nested()` is conceptually a transaction savepoint, not a Prisma model method. The `Engine` owns a pool; a Session is not itself a raw connection.

## Python concepts I should learn from this technology

Generic type annotations (`Mapped[...]`); declarative classes; context managers; generators for dependencies; `try/finally`; ORM relationships; exceptions; `with`; transaction scopes.

## Debugging questions

1. What session owns this ORM object, and has it been committed/flushed?
2. Where is the transaction or SAVEPOINT boundary?
3. Is this failure a constraint violation, connection failure, or object-state issue?
4. Does this query load bounded data, or `.all()` at unbounded scale?

## Break-the-system exercise

### Experiment
Temporarily remove `session.begin_nested()` from `ingest_csv`, import a CSV containing a duplicate provider/external reference, and compare the result.

### Expected observation
Pay attention to whether one failed insert affects later rows and what happens to the surrounding session transaction.

### Questions to answer
1. Why is a SAVEPOINT narrower than the job transaction? 2. When does `flush()` happen? 3. Which exception is caught? 4. What data was committed?

### What to investigate next
Read `app/database.py`, `app/models.py`, `app/services.py`, and the initial migration.

---

# Technology: PostgreSQL

## Problem

Imported transactions, job state, findings, and AI explanations need durable shared truth across API/worker processes. The system must enforce concurrency-sensitive invariants even when two workers or requests disagree.

## Why it exists here

Compose runs `postgres:17-alpine`; API and worker use `postgresql+psycopg://...@postgres:5432/finops`. `Transaction` defines a provider/external-reference unique constraint and indexes for internal reference and customer/timestamp. `ImportJob.idempotency_key` is unique. The JSON type becomes PostgreSQL `JSONB` via `JSON().with_variant(JSONB, "postgresql")`, while retaining JSON for SQLite learning fallback. `Finding` links to `Transaction`; `/findings` applies offset/limit pagination. Alembic contains an initial relational schema. Local default config is SQLite, so PostgreSQL-specific behavior is not exercised unless Compose/another PostgreSQL URL is used.

## What happens without it?

Current: `API and worker → shared PostgreSQL source of truth → constraints/indexes`.

Without it: `API/worker → local files/in-memory structures` or a different database. Workers would not safely coordinate durable jobs/transactions, uniqueness could become best-effort application code, and restarts lose state. Removing PostgreSQL but leaving SQLite is useful for local tests, not equivalent production behavior.

## Alternatives

* **SQLite:** perfect for the repository's local default/basic tests; weak fit for independent deployed API/worker concurrency and PostgreSQL JSONB behavior.
* **MySQL:** viable relational source of truth; changes dialect, JSON/index/query details and does not add learning value here.
* **Managed PostgreSQL (RDS/Cloud SQL/Railway):** same database engine with operational offload; deployment choice, not an architectural substitute.
* **Document DB:** flexible documents, but poor fit for relational job/transaction/finding links and strong unique/transaction needs.

## Why this project chose it

* **Technical reason:** durable transactions, relational foreign keys, unique constraints, indexes, numerics, and JSONB fit financial records/evidence.
* **Ecosystem reason:** first-class SQLAlchemy/Alembic/psycopg support and ordinary Docker availability.
* **Learning reason:** teaches why database guarantees outrank application assumptions.

Tradeoff: it adds an operated stateful service, migrations, backups, connection limits, and query planning concerns.

## When I would NOT use it

Do not provision PostgreSQL for a disposable local parsing utility with no shared/durable state. Do not store raw multi-gigabyte files in transaction JSONB simply because JSONB exists. For warehouse-scale aggregation, use PostgreSQL selectively and send analytical workloads to an appropriate warehouse; `reconcile`'s Python loop is not an automatically scalable analytics design.

## Failure modes

* Unavailable PostgreSQL breaks readiness, API persistence, and workers. Compose health checks gate startup but do not recover runtime outages.
* Unique constraints prevent duplicate provider/external rows and duplicate idempotency keys even if application checks race.
* Index removal does not change correctness but harms lookups; the current reconciliation query does not use the declared indexes because it loads all rows. **Current limitation.**
* JSONB stores flexible evidence/AI fields, but current code does not query/index their contents.
* No `SELECT FOR UPDATE`/explicit locking exists. **Current limitation:** job/finding state updates can race at high concurrency.

## Node.js / TypeScript analogy

This is the same PostgreSQL role as in NestJS: durable shared source of truth, not a cache. Difference is around client behavior: SQLAlchemy's session identity map/unit-of-work differs from Prisma's generated client or TypeORM's repository APIs. The unique constraints are database facts regardless of whether FastAPI, NestJS, or a worker performs the write.

## Python concepts I should learn from this technology

`Decimal`; UUID/datetime types; enums; ORM declarations; foreign keys/relationships; transaction context managers; query construction; pagination parameters.

## Debugging questions

1. Is PostgreSQL or the SQLite fallback actually backing this process?
2. Which invariant is database-enforced versus only checked in Python?
3. Does the query use an index and return bounded rows?
4. Could two workers update this record concurrently?

## Break-the-system exercise

### Experiment
On a disposable PostgreSQL database, drop `ix_transactions_customer_timestamp`, load enough data to query by those fields, and compare `EXPLAIN ANALYZE` before/after.

### Expected observation
Observe query plan/cost/latency changes, not correctness changes.

### Questions to answer
1. Which endpoint currently queries these fields? 2. Why retain an index unused by current code? 3. What is write cost? 4. When would a composite index order matter?

### What to investigate next
Read `app/models.py`, migration `0001_initial.py`, and `docs/deployment.md`.

---

# Technology: Redis

## Problem

Long-running work needs a broker that can accept a task from the API and make it available to independent Celery workers. This repository does **not** use Redis as a cache.

## Why it exists here

`app/workers.py` creates `Celery("finops", broker=settings.redis_url, backend=settings.redis_url)`. `create_import`, `queue_reconciliation`, and `queue_investigation` call `.delay()`, publishing tasks through that broker/backend. `compose.yaml` runs Redis 7 and sets both API and worker `FINOPS_REDIS_URL` to the Compose service. The database—not Redis—owns ImportJob/Transaction/Finding state; Redis is message/result infrastructure. No code reads a Celery `AsyncResult`, so the result backend exists by configuration but is not exposed through an application status API.

## What happens without it?

Current: `API → Redis broker → Celery worker → PostgreSQL`.

Without it: `API → synchronous service call → PostgreSQL`, or another broker implementation. Upload requests would own task duration and fail/restart behavior would be coupled to web workers. Redis removal also removes configured Celery result transport, even though current API does not read it.

## Alternatives

* **RabbitMQ + Celery:** a dedicated broker with stronger messaging focus; more operational complexity, but often preferred for complex routing/durability.
* **SQS + Celery:** managed AWS transport; reduces broker operations but ties the deployment to AWS semantics.
* **PostgreSQL-backed job table/poller:** avoids Redis for modest workloads; needs locking/polling and is not implemented here.
* **BullMQ + Redis in Node:** same broad broker role, only if the worker is TypeScript rather than Celery/Python.

## Why this project chose it

* **Technical reason:** one lightweight local service satisfies current Celery broker and result backend needs.
* **Ecosystem reason:** `celery[redis]` is already in the dependencies and Redis has a straightforward Compose image.
* **Learning reason:** separates durable business state from queue transport state.

Tradeoff: Redis becomes an operational dependency and its durability configuration affects task-loss behavior.

## When I would NOT use it

Do not add Redis because it is “fast” when PostgreSQL queries, indexes, or in-process caching solve the actual problem. Do not use it for a low-volume task that can finish safely in a request or a scheduled command. Do not treat Redis queue messages as the financial system of record.

## Failure modes

* If Redis is down, `.delay()` cannot publish; the import job may already be committed and remain queued. **Current limitation:** no transactional outbox/retry publisher repairs that gap.
* Redis restart/eviction/persistence settings can lose queued/result data; no Redis persistence policy is specified in `compose.yaml`. **Current limitation.**
* Workers cannot consume while Redis is unavailable; PostgreSQL data remains intact.
* Result backend growth can consume Redis memory; this repository never expires/reads task results explicitly. **Current limitation.**

## Node.js / TypeScript analogy

Redis has the same role it often has behind BullMQ: a shared message/state transport between producer and worker. Difference: Celery controls task serialization, acknowledgement, retry and result behavior rather than a Node BullMQ worker API. Here it is explicitly **not** a cache or authoritative import status store; `ImportJob.status` in SQLAlchemy/PostgreSQL is that application state.

## Python concepts I should learn from this technology

Environment configuration; object construction; distributed failure boundaries; task serialization; exception/retry classification; separation of process-local and shared state.

## Debugging questions

1. Is Redis reachable from both API and worker using the same URL?
2. Did the database commit happen before task publication failed?
3. Am I looking for task transport state or authoritative job state?
4. Is task/result retention exhausting Redis memory?

## Break-the-system exercise

### Experiment
Stop the Redis Compose service, submit an import, then inspect the database and API/worker logs after restarting Redis.

### Expected observation
Distinguish an already-created `ImportJob` from a task that was never successfully published.

### Questions to answer
1. Which state survived? 2. Did the route return a response? 3. How would an outbox change recovery? 4. Is retrying publication safe with the idempotency key?

### What to investigate next
Read `app/main.py`, `app/workers.py`, `.env.example`, and `compose.yaml`.

---

# Technology: Celery

## Problem

CSV parsing and reconciliation can be long-running and should not hold an HTTP request open. They need a process that can be restarted/scaled separately, a queue boundary, task time limits, and some retry/idempotency behavior.

## Why it exists here

The Celery application and three tasks live in `app/workers.py`: `import_file`, `run_reconciliation`, and `investigate_finding`. API routes publish each using `.delay()`. `import_file` transitions an `ImportJob` from queued to processing to completed/failed, uses `task_acks_late=True`, has a 300-second time limit, and skips already completed jobs. It autoretries `OSError` with exponential backoff up to three retries. `investigate_finding` skips an existing explanation and autoretries only `OSError` up to two times. Compose runs a separate worker container.

## What happens without it?

Current: `POST /imports → ImportJob commit → Celery publish → worker → CSV/database`.

Without it: `POST /imports → CSV/database before response`. Request timeouts, API restarts, limited web concurrency, and poor backpressure become part of ingestion reliability. A cron/CLI could replace Celery for scheduled batch work but not immediate queue-driven import execution.

## Alternatives

* **FastAPI BackgroundTasks:** useful for very short in-process follow-up; not durable across API restart and unsuitable for large imports.
* **RQ/Dramatiq:** simpler Python worker ecosystems; less feature/configuration surface but a different learning/runtime choice.
* **Temporal:** durable workflow orchestration; valuable for multi-step compensation but too heavy for the current three tasks.
* **BullMQ:** the Node equivalent; appropriate for TypeScript workers but not this Python application.

## Why this project chose it

* **Technical reason:** separates API latency from worker capacity and provides task retry/time-limit hooks.
* **Ecosystem reason:** mature Python queue library with Redis support and clear worker CLI.
* **Learning reason:** demonstrates process boundaries, at-least-once delivery implications, and idempotency beyond `async def`.

Tradeoff: it adds broker/worker monitoring, serializable task arguments, deployment coordination, and duplicate-delivery thinking.

## When I would NOT use it

Do not add Celery for an operation that completes in milliseconds or when a simple scheduled CLI is enough. Avoid it if the team cannot operate a broker/worker and a managed job service fits better. Do not use a task queue as a substitute for designing idempotent database state.

## Failure modes

* `task_acks_late=True` means a worker crash can cause redelivery; `import_file` avoids work only if status is already completed. It can still duplicate partial work before completion, relying partly on transaction uniqueness. **Current limitation:** no explicit job lock/lease or atomic task claim.
* Generic import exceptions set job failed and re-raise; only `OSError` is automatically retried. Parse/schema/database errors are not retried by Celery.
* The 300-second time limit can terminate a large import. **Current limitation:** no timeout-specific ImportJob error/recovery workflow.
* `run_reconciliation` can create new findings every invocation; it has no idempotency/deduplication guard. **Current limitation.**
* AI configuration/validation failures are not persisted to a finding status. **Current limitation.**

## Node.js / TypeScript analogy

Celery is BullMQ-style queue-worker infrastructure: `.delay()` resembles enqueueing a named job and a separate process consumes it. Similarity: HTTP producer and worker do not share memory. Difference: Celery task decorators register Python callables; retry acknowledgement and result behavior are Celery configuration, not an async Promise chain. `asyncio.run` inside a worker does not turn Celery into an asyncio worker system.

## Python concepts I should learn from this technology

Decorators; module-level application objects; callables; exceptions; context managers; sync process execution; serialization constraints; idempotency guards; environment configuration.

## Debugging questions

1. Was the task published, consumed, started, retried, or dead/failed?
2. Can this task be delivered twice, and what database guard makes that safe?
3. Is the exception an `OSError` eligible for configured retry?
4. Did task timeout/crash leave business state in `processing`?

## Break-the-system exercise

### Experiment
Temporarily call `ingest_csv(session, ...)` directly in `create_import` instead of `import_file.delay`, using a sizeable disposable CSV.

### Expected observation
Watch request duration, API responsiveness, error ownership, and what happens if you interrupt the API process.

### Questions to answer
1. Who now owns retries? 2. What status should the route return? 3. Is upload work still horizontally scalable? 4. What is lost on API restart?

### What to investigate next
Read `app/main.py`, `app/workers.py`, `compose.yaml`, and the queue section in `docs/learning-guide.md`.

---

# Technology: asyncio

## Problem

An AI/external-investigation layer can spend most time waiting on network I/O. It needs bounded concurrent waits, deadlines, and cancellation behavior without dedicating a thread to every socket wait. The current repository demonstrates that pattern, while its actual ingestion remains synchronous pandas/database work.

## Why it exists here

`bounded_fetch` in `app/services.py` is the intentional concurrency experiment: it creates tasks, uses `asyncio.gather`, gates starts with `Semaphore`, scopes each wait with `asyncio.timeout`, and awaits simulated I/O (`sleep`). `app/ai.py` uses `AsyncOpenAI`, awaits its parse call, adds a 20-second outer timeout and 15-second client timeout. `investigate_finding` is a synchronous Celery task that bridges to the coroutine using `asyncio.run`. There are no async FastAPI routes and no general async SQLAlchemy engine.

## What happens without it?

Current: `worker → asyncio event loop → concurrent bounded external waits`.

Without it: `worker → sequential blocking request → next request`. External investigation throughput falls as individual network waits accumulate. The application can still import/reconcile because those paths are synchronous; `asyncio` is not required for pandas parsing.

## Alternatives

* **Synchronous OpenAI client:** simpler for one occasional request; serializes waiting and makes concurrency require threads/processes.
* **ThreadPoolExecutor:** useful for blocking I/O libraries; adds thread/resource coordination and is not present in current code.
* **AnyIO:** FastAPI ecosystem abstraction over asyncio/trio; useful in ASGI code but not necessary for this focused example.
* **Node Promise.all + p-limit:** closest TypeScript expression; only available if this is a Node worker.

## Why this project chose it

* **Technical reason:** provides bounded concurrent I/O and explicit timeout behavior for the async client.
* **Ecosystem reason:** `AsyncOpenAI` is coroutine-based and Python 3.12 provides `asyncio.timeout`.
* **Learning reason:** demonstrates that concurrency is not the same as parallel CPU execution.

Tradeoff: it introduces cancellation/timeout semantics and must not be used to disguise CPU-bound pandas or Python loops as async.

## When I would NOT use it

Do not introduce coroutine orchestration for one local CPU calculation or one infrequent network call where synchronous code is clearer. Do not run blocking pandas, SQLAlchemy sync session calls, or CPU-heavy reconciliation inside an async route and expect throughput. Use process workers/Celery for CPU/long work; use a thread bridge only for blocking I/O libraries.

## Failure modes

* Per-call `asyncio.timeout(2)` in `bounded_fetch` cancels a slow operation; the caller receives the error from `gather` because `return_exceptions=True` is not used.
* The AI client has nested 15s/20s timeouts; a timeout failure is not an `OSError`, so current Celery configuration does not automatically retry it. **Current limitation.**
* A semaphore limits in-flight work but `bounded_fetch` still creates all tasks eagerly; enormous input can still allocate many task objects. **Current limitation.**
* `asyncio.run` cannot run inside an already-running event loop, though it is invoked from a synchronous Celery task today. Changing worker execution context needs care.

## Node.js / TypeScript analogy

`async def`/`await`, `create_task`, and `gather` are closest to async functions, promises, and `Promise.all`; `Semaphore` resembles `p-limit`. Difference: Python has one event loop per thread by default and synchronous CPU/Python code blocks it; the GIL also means threads usually do not accelerate pure Python CPU work. A coroutine is not executing until it is awaited/scheduled, unlike treating every Promise creation as a generic solution.

## Python concepts I should learn from this technology

Coroutines; `async def`/`await`; event loops; task creation; `gather`; async context managers; semaphores; timeout/cancellation; sync-to-async bridging with `asyncio.run`.

## Debugging questions

1. Is this operation I/O-bound, CPU-bound, or blocking synchronous code?
2. Is the coroutine actually awaited/scheduled?
3. Which timeout fired, and is it retryable?
4. Is semaphore concurrency bounded at the right level?
5. Did cancellation clean up the network client/resource?

## Break-the-system exercise

### Experiment
Change `bounded_fetch` to `return [await one(delay) for delay in delays]` and time it against the current implementation with several equal delays.

### Expected observation
Compare elapsed wall time and concurrency; do not infer anything about CPU parallelism from the result.

### Questions to answer
1. What does the semaphore control now? 2. Why does sequential await change elapsed time? 3. What cancels on timeout? 4. Would pandas improve the same way?

### What to investigate next
Read `app/services.py`, `app/ai.py`, and `docs/node-to-python.md`.

---

# Technology: pandas

## Problem

Transaction sources are files, potentially too large to load into ordinary Python lists. The system needs file parsing, missing-value handling, duplicate candidate detection, and a path from tabular provider columns to one record-normalization function.

## Why it exists here

`csv_chunks` uses `pd.read_csv(..., chunksize=1000)` and yields DataFrames. `ingest_csv` calls `frame.drop_duplicates(subset=["provider", "external_reference"])`, then converts each chunk to record dictionaries. `normalize_record` uses `pd.notna` to remove missing values before Pydantic parsing. pandas is currently used only for CSV—although `openpyxl` is a dependency, no Excel importer exists. There are no DataFrame joins, grouping, aggregation, or merge operations in current implementation.

## What happens without it?

Current: `CSV → pandas chunk/DataFrame → deduplicated records → Pydantic → database`.

Without it: `CSV module iterator → Python dicts/sets → Pydantic → database`. For a simple stable CSV that may be perfectly reasonable; pandas here mainly supplies chunked tabular parsing and convenient vectorized duplicate/missing-data operations. It is not the persistence layer or source of truth.

## Alternatives

* **Python `csv` module:** streaming and dependency-free; suitable for simple CSV schema, but missing pandas table operations.
* **Polars/PyArrow:** columnar/high-performance alternatives for larger analytical transforms; add different APIs and are unjustified until profiling identifies a need.
* **PostgreSQL `COPY` + SQL transforms:** excellent for very large trusted batches; harder to combine with row-level Pydantic validation/error reporting.
* **SQL/pandas hybrid:** load raw staging data then aggregate/join in SQL; appropriate when reconciliation becomes set-based at scale.

## Why this project chose it

* **Technical reason:** chunking prevents whole-file memory loading and DataFrames make file-shaped cleanup concise.
* **Ecosystem reason:** pandas is mature for CSV/Excel operational data and already fits the project's learning target.
* **Learning reason:** makes clear that a DataFrame is a data-processing structure, not a replacement for PostgreSQL transactions.

Tradeoff: `to_dict(orient="records")` returns to per-row Python work and can be costly; it is intentionally readable rather than maximum-throughput bulk loading.

## When I would NOT use it

Do not create a DataFrame just to map ten already-validated Python dicts. Prefer SQL for relational filtering/grouping already in PostgreSQL, and plain generators for simple streaming transforms. For multi-gigabyte/columnar workloads, benchmark Polars/PyArrow/COPY instead of assuming pandas is enough.

## Failure modes

* A file without the duplicate-subset columns makes `drop_duplicates` fail outside the row-level `try`. **Current limitation:** the job fails rather than returning a structured header validation error.
* Chunking limits each DataFrame, but duplicate detection only applies within a chunk; PostgreSQL unique constraint handles cross-chunk duplicate provider/external references.
* `pd.notna` filters missing values, but odd source formatting can still cause Pydantic rejection.
* Malformed CSV/parser memory/resource behavior is not explicitly configured. **Current limitation:** no file size, content-type, encoding, or quarantine/error-report policy exists.

## Node.js / TypeScript analogy

A DataFrame is closer to a batch-oriented table transform in a Node ETL library than an array of objects. Similarity: you can map/filter/deduplicate tabular inputs. Difference: pandas operations are often vectorized over columns and chunked readers produce DataFrames; converting to dicts deliberately crosses back into Python object iteration. The `csv` module would be closer to Node stream row parsing.

## Python concepts I should learn from this technology

Generators (`yield from`); iterators; DataFrames; dict/list comprehensions; per-row exception handling; function boundaries; `Decimal`/Pydantic parsing; resource/memory reasoning.

## Debugging questions

1. Is a failure in CSV parsing, DataFrame transform, Pydantic normalization, or database insertion?
2. Is duplicate handling within a chunk or enforced by the database across chunks?
3. Is this transformation better vectorized, a plain generator, or SQL?
4. How large is a chunk and where is memory actually allocated?

## Break-the-system exercise

### Experiment
Create a disposable CSV with a required header removed, submit it, and observe the ImportJob and worker behavior.

### Expected observation
See the difference between file-level DataFrame errors and row-level validation errors.

### Questions to answer
1. Does the task mark the job failed? 2. Which exception scope catches it? 3. How would you validate headers before work begins? 4. What would a user-facing error report need?

### What to investigate next
Read `csv_chunks`, `ingest_csv`, `TransactionInput`, and `app/workers.py`.

---

# Technology: Docker

## Problem

The API, worker, PostgreSQL, and Redis are distinct processes with compatible versions/configuration requirements. A developer should be able to reproduce their topology without installing every service manually.

## Why it exists here

`Dockerfile` builds a Python 3.12 image, installs `uv`, runs `uv sync --frozen --no-dev`, copies source, and starts Uvicorn by default. `compose.yaml` defines `postgres`, `redis`, `api`, and `worker`; API runs migration then Uvicorn, worker starts Celery, and both receive internal PostgreSQL/Redis URLs. PostgreSQL and Redis health checks gate API/worker startup. `.env.example` supplies environment names. **Current limitation:** no Compose volume is declared, so PostgreSQL data is ephemeral across `docker compose down`/container recreation; no production image hardening or non-root user is configured.

## What happens without it?

Current: `Compose → four configured containers on a shared network`.

Without it: each developer installs/runs Python, PostgreSQL, Redis, API, and worker manually and must reproduce networking/environment values. Production can use managed services without Docker Compose, but containers still provide an artifact boundary in the documented deployment paths.

## Alternatives

* **Native processes + system package managers:** fastest for a personal script; setup drift becomes likely for this multi-service app.
* **Dev Containers:** wraps the same container idea in editor tooling; adds editor/platform coupling.
* **Kubernetes:** useful after operational/scaling needs justify it; overkill for local learning and absent here.
* **Managed PaaS builds:** can remove local Dockerfile ownership, but limits reproducibility/control.

## Why this project chose it

* **Technical reason:** expresses API/worker/broker/database process boundaries and startup dependencies.
* **Ecosystem reason:** official images exist for Python, PostgreSQL, and Redis; Compose is familiar locally.
* **Learning reason:** translates “one Node API process” into an explicit distributed local topology.

Tradeoff: Docker does not make data durable, production-safe, or cloud-ready by itself; networking, secrets, volumes, migrations, and observability remain engineering work.

## When I would NOT use it

Do not require Docker for a single short script with no external services. Do not use Compose as a production orchestration plan merely because it starts locally. If a team is already standardized on managed dev environments, a native/remote workflow may be simpler.

## Failure modes

* Missing `.env` causes Compose env-file startup failure.
* `uv sync --frozen` requires a lockfile, but no `uv.lock` is tracked. **Current limitation:** the Docker build is likely to fail until a lockfile is generated/committed or the command changes.
* API performs `alembic upgrade head` on startup; multiple API replicas could race migration application. **Current limitation:** migrations should be a single release job in real deployment.
* Redis/Postgres health checks only gate startup; application dependencies can fail later.
* Docker was not available in the prior execution environment, so this Compose topology was not verified there. **Current limitation.**

## Node.js / TypeScript analogy

This is the same Docker/Compose role as a Node API plus BullMQ worker/Postgres/Redis stack: image is a packaged runtime filesystem/process command, container is a running instance, Compose is local multi-service wiring. Difference: the image builds an isolated Python `uv` environment rather than installing npm `node_modules`; Python imports resolve from that interpreter environment.

## Python concepts I should learn from this technology

Environment variables; filesystem paths; process entrypoints; virtual environments (`uv`); module import strings (`app.main:app`, `app.workers.celery_app`); configuration isolation.

## Debugging questions

1. Is the failing process API, worker, PostgreSQL, or Redis?
2. Which environment URL does the container actually receive?
3. Is startup blocked by a health check, migration, dependency install, or application error?
4. Does required state survive container recreation?

## Break-the-system exercise

### Experiment
Temporarily set the API `FINOPS_REDIS_URL` in `compose.yaml` to a wrong hostname and start the stack.

### Expected observation
Compare API startup/health behavior with what happens only when `/imports` attempts `.delay()`.

### Questions to answer
1. Which service owns the connection attempt? 2. Why may health checks still pass? 3. Which configuration should differ locally vs production? 4. How would you surface this earlier?

### What to investigate next
Read `Dockerfile`, `compose.yaml`, `.env.example`, `app/config.py`, and `docs/deployment.md`.

---

# Technology: LLM layer

## Problem

Deterministic code can establish evidence such as a duplicate or high amount, but an operator may want a readable investigation summary and recommended action. Natural-language synthesis is probabilistic and must not become the authority for whether money records match.

## Why it exists here

`reconcile` and `detect_anomalies` in `app/services.py` create `Finding` records with enum outcomes/evidence. `app/ai.py` sends only supplied evidence plus `SYSTEM_PROMPT` to `AsyncOpenAI`; it asks the SDK to parse into `InvestigationExplanation`. `investigate_finding` in `app/workers.py` skips a finding that already has an explanation, runs the async call, and stores `model_dump()` in `Finding.ai_explanation`. `POST /findings/{finding_id}/investigations` queues it. `ExplanationClient` Protocol exists in `app/services.py`, but the actual `investigate` function does not implement/inject that protocol. **Current limitation:** there is no true provider abstraction or test fake wired into the task.

## What happens without it?

Current: `transaction data → deterministic finding/evidence → queued LLM explanation → validated JSON`.

Without it: `transaction data → deterministic finding/evidence → human/operator UI`. Reconciliation correctness is preserved; only the optional explanation layer is absent. Removing the LLM should never remove duplicate/mismatch/anomaly detection.

## Alternatives

* **Rules/templates:** deterministic prose from evidence; cheap/auditable but less flexible narrative.
* **Human investigation workflow:** strongest judgement/accountability; slower and higher operational cost.
* **Another structured-output LLM provider:** same boundary pattern, but requires an adapter/test suite for its SDK/error model.
* **No AI:** appropriate when evidence itself is sufficient or data sensitivity/cost prohibits external models.

## Why this project chose it

* **Technical reason:** Pydantic structured output makes probabilistic response persistence safer than arbitrary JSON.
* **Ecosystem reason:** the OpenAI Python SDK has an async parse API compatible with Pydantic models.
* **Learning reason:** demonstrates a safe boundary where model output supports operators but cannot decide ledger truth.

Tradeoff: network/service dependence, latency, cost, data-sharing risk, prompt/model changes, and output validation still exist even with structured parsing.

## When I would NOT use it

Do not use an LLM to determine financial reconciliation truth, enforce constraints, or replace deterministic amount/reference comparisons. Avoid it where data cannot be sent to a provider, explanations must be fully deterministic/auditable, or the operator benefit does not justify latency/cost. A template can be better for a fixed evidence schema.

## Failure modes

* Missing `FINOPS_OPENAI_API_KEY` raises `RuntimeError`; the task does not save a finding-level failure state. **Current limitation.**
* The SDK has `max_retries=2`, a 15-second client timeout, and an outer 20-second asyncio timeout. A malformed/no parsed response raises `ValueError` before database write.
* Celery autoretry is configured only for `OSError`; many OpenAI timeout/validation/provider errors will not retry. **Current limitation.**
* `str(evidence)` is sent as prompt content; current code has no redaction/classification policy. **Current limitation:** do not assume financial metadata is safe to send.
* A second task sees existing `ai_explanation` and skips, but concurrent tasks can both observe null before commit. **Current limitation:** no lock/unique investigation claim.

## Node.js / TypeScript analogy

This resembles calling an LLM SDK with a Zod/JSON-schema structured-output contract inside a BullMQ worker. Similarity: external model output is parsed before persistence and a worker isolates latency. Difference: Python uses a Pydantic class both as runtime parser and SDK response format, plus `asyncio` timeout/coroutine mechanics. The `Protocol` is structurally typed, but current production path does not actually depend on it.

## Python concepts I should learn from this technology

Async functions; `await`; timeouts; `try/finally`; async client cleanup; Pydantic parsing/model dumps; Protocols; environment configuration; exception taxonomy; structured logging `extra` fields.

## Debugging questions

1. Was the finding outcome created deterministically before AI was requested?
2. Which timeout/retry layer handled the provider failure?
3. Did the SDK return a parsed `InvestigationExplanation`, not merely text/JSON?
4. Is evidence safe/minimized for an external provider?
5. Could duplicate tasks write conflicting explanations?

## Break-the-system exercise

### Experiment
In a disposable local test/fake setup, make `investigate` return content that cannot satisfy `InvestigationExplanation` (for example confidence above 1) and queue an investigation.

### Expected observation
Trace where structured parsing rejects it and whether the finding gets an explanation or a persisted failure state.

### Questions to answer
1. Did deterministic evidence change? 2. Which exception type results? 3. Is it retryable? 4. What operator-visible state is missing? 5. Where would a provider abstraction help testing?

### What to investigate next
Read `app/ai.py`, `app/schemas.py`, `app/workers.py`, and `docs/learning-guide.md`.

---

# Cross-cutting lessons

1. **Deterministic first, probabilistic second.** `reconcile`/`detect_anomalies` decide outcomes; AI receives evidence after that, so an explanation cannot be mistaken for ledger truth.
2. **Long work leaves HTTP.** The `202` import route commits a job then publishes a task; API capacity and worker capacity are separate concerns.
3. **Idempotency is layered.** The import header/job unique key, completed-job guard, and transaction unique constraint each address a different duplicate path; they do not fully solve partial worker crash recovery.
4. **The database is source of truth.** SQL records own jobs, transactions, and findings. Redis transports tasks; pandas transforms a file; neither owns financial state.
5. **Validate at boundaries.** Pydantic validates file records/AI structures; database constraints enforce concurrent durable invariants; they are complementary rather than interchangeable.
6. **Concurrency is not parallelism.** `asyncio` overlaps I/O waits; it does not make pandas/reconciliation CPU work parallel. Celery moves work into another process; that is a different tool.
7. **Retries need semantics.** Celery only retries `OSError` in current tasks. Retrying a malformed CSV is noise; retrying transient network failure can help. Current code still needs stronger failure state/recovery.
8. **Infrastructure follows the problem.** Redis/Celery exist for independent background execution, PostgreSQL for durable relational constraints, pandas for file-shaped transforms—not because each is fashionable.
9. **Python features are tools.** Generator dependencies release sessions, context managers scope transactions/files, decorators register routes/tasks, and Protocol advertises an adapter seam.
10. **Ownership must not overlap.** FastAPI owns HTTP, Pydantic parsing, SQLAlchemy persistence mechanics, PostgreSQL durable truth, Celery execution, Redis transport, pandas file transforms, and the LLM optional explanation. Blurring them makes failures harder to diagnose.

# How this maps to my Node.js experience

| Python component | Node.js conceptual equivalent |
|---|---|
| FastAPI route + `Depends` | Nest controller + scoped provider/pipe |
| Pydantic model | DTO plus Zod/class-validator runtime schema |
| SQLAlchemy `Engine`/`Session` | TypeORM EntityManager/DataSource or Prisma client transaction territory |
| PostgreSQL constraints/indexes | The same PostgreSQL guarantees behind a Node ORM |
| Celery task/worker | BullMQ-style producer and separate worker |
| Redis broker/backend | Redis transport for queue/job infrastructure, not this app's cache |
| `asyncio` task/gather/semaphore | Promise, `Promise.all`, and `p-limit`-style I/O concurrency |
| pandas chunk/DataFrame | Batch/ETL table transform, not a Node request object array |
| Docker Compose | Node API + worker + Postgres + Redis local topology |
| `InvestigationExplanation` | Zod schema protecting LLM structured output |

## Where the analogy breaks

Nest's container/class/decorator model is not FastAPI's callable generator dependency model. Python type hints are not runtime schemas until Pydantic consumes them. SQLAlchemy Sessions are explicit unit-of-work/identity-map objects, not automatically equivalent to Prisma calls. `asyncio` has coroutine/event-loop rules and CPU/GIL implications different from Node's JavaScript runtime. Celery task acknowledgement/retry semantics are not a Promise lifecycle. Finally, no Node analogy removes the need for PostgreSQL constraints or idempotency in distributed work.

# Questions I should be able to answer after studying this repository

1. Why does `POST /imports` return `202` rather than wait for parsing?
2. What makes an import idempotent, and which duplicate paths remain?
3. What owns authoritative import status: Redis, Celery result backend, or `ImportJob`?
4. What happens if Redis is unavailable after `ImportJob` commits but before `.delay()` succeeds?
5. What transaction boundary isolates an invalid transaction row?
6. Why does the provider/external-reference unique constraint matter even after pandas `drop_duplicates`?
7. Which failures in `import_file` will Celery automatically retry, and why?
8. What state can a worker crash leave behind?
9. Why should the LLM never determine `Outcome`?
10. How does `InvestigationExplanation` protect persistence, and what cannot it protect?
11. What are the two timeout layers in the AI call?
12. Why can an `asyncio` function still cause poor performance?
13. What does the semaphore in `bounded_fetch` limit, and what does it not limit?
14. When is plain Python `csv` preferable to pandas here?
15. Which current pandas operations are vectorized and which return to per-row Python work?
16. Which fields/indexes are currently declared but not used by the reconciliation query?
17. Why is SQLite fallback useful but not production-equivalent to Compose PostgreSQL?
18. Why can API startup migrations be risky with multiple replicas?
19. What does `pool_pre_ping` address, and what database failures remain?
20. At 10× transaction volume, which query/ingestion/reconciliation assumptions should be profiled first?
