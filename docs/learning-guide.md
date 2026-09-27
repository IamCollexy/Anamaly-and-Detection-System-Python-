# Progressive learning guide

## 1. API and validation
**Problem:** input is untrusted. Read `TransactionInput` then `/imports`. Pydantic is DTO/runtime validation, not merely TypeScript types. **Break it:** remove the currency validator and observe inconsistent grouping. **Exercise:** add an ISO allow-list.

## 2. Database ownership
`get_session` is a scoped Nest provider analogue. The generator's `finally` closes resources. A Session is a unit of work; the engine pool manages connections. **Exercise:** add transaction pagination and inspect its SQL.

## 3. Files and pandas
`csv_chunks` is an iterator/generator, limiting memory. pandas catches cheap in-memory duplicates; PostgreSQL's unique constraint is the race-safe guarantee. **Exercise:** create an Excel adapter that emits records to `normalize_record`.

## 4. Queue and recovery
HTTP stores `ImportJob`, then Celery gets its id. Synchronous imports would tie up a web process and fail with request deadlines. Tasks have time limits/retries and completion guards. **Exercise:** force one retry and inspect state.

## 5. Deterministic before AI
Reconciliation creates facts; AI can only explain evidence and must parse through `InvestigationExplanation`. **Exercise:** fake malformed AI output and assert Pydantic rejects it.

## 6. Async and CPU work
`bounded_fetch` is `Promise.all` plus `p-limit`: tasks, `gather`, semaphore, timeout, and cancellation propagation. Avoid CPU/pandas work in it. Python's GIL changes CPU-thread expectations; use a process pool/Celery. **Exercise:** compare sequential sleep calls with bounded concurrent calls.

## Break-the-system investigations
1. Remove Redis. 2. Call ingestion from the HTTP route. 3. Stop the worker. 4. Drop the customer/time index. 5. Replace `gather` with a loop. 6. Return malformed AI JSON. 7. Kill a worker mid-job. 8. Reuse an idempotency key. 9. Upload invalid rows. 10. Import a multi-million row CSV. Record symptoms before looking for solutions.
