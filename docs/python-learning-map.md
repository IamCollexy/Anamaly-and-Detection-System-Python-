# Python learning map

| Concept | Code | Production purpose |
|---|---|---|
| Pydantic runtime parsing | `app/schemas.py` | Validates untrusted file data; hints alone do not. |
| Dict comprehensions/unpacking | `normalize_record` | Maps inconsistent provider fields to one canonical DTO. |
| Dataclass | `ImportStats` | A small immutable service result, not an ORM/API object. |
| Generator/context manager | `csv_chunks`, `get_session` | Bounds CSV memory and closes database resources. |
| Protocol | `ExplanationClient` | Defines an LLM adapter seam without an artificial inheritance tree. |
| asyncio | `bounded_fetch` | Tasks, semaphores and timeout for bounded external I/O. |
| Transaction/SAVEPOINT | `ingest_csv` | One bad row does not poison an import. |
| Decorator | `@celery_app.task` | Registers worker-callable queue tasks. |
| FastAPI DI | `get_session` in routes | Request-scoped session lifecycle. |
| pytest parametrization | `tests/test_services.py` | Tests the normalization contract compactly. |
