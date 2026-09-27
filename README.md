# FinOps Intelligence & Reconciliation Platform

Files become validated transactions, PostgreSQL stores them, deterministic reconciliation/anomaly logic creates findings, Celery moves slow work away from HTTP, and a future LLM adapter explains—not decides—evidence.

## Architecture
`FastAPI → Pydantic → ImportJob → Celery/Redis → pandas chunks → SQLAlchemy/PostgreSQL → findings → validated AI explanation`.

FastAPI provides HTTP/DI; Pydantic validates runtime data; SQLAlchemy owns unit-of-work transactions; pandas streams operational files; Redis/Celery prevents huge imports from occupying an HTTP worker. The LLM boundary is `InvestigationExplanation`, so arbitrary JSON never reaches the database.

## Setup
```bash
uv sync --all-groups
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
# another terminal, with Redis available
uv run celery -A app.workers.celery_app worker --loglevel=INFO
```
For the full topology: `cp .env.example .env && docker compose up --build`. This environment lacks Docker, so Compose could not be executed here.

## Flow
```bash
curl -F file=@sample.csv -H 'Idempotency-Key: demo-001' http://localhost:8000/imports
curl http://localhost:8000/imports/<job-id>
curl -X POST http://localhost:8000/reconciliations
curl http://localhost:8000/findings
```
CSV fields match `TransactionInput`; `reference`, `customer`, and `type` normalize to canonical fields. Excel/JSON/SQL dump support is intentionally adapter work: emit records into the same normalizer, never duplicate domain logic or execute arbitrary SQL dumps.

## Quality and docs
```bash
uv run ruff check .
uv run pytest
```
Read [learning map](docs/python-learning-map.md), [Node bridge](docs/node-to-python.md), [learning guide](docs/learning-guide.md), and [deployment guidance](docs/deployment.md). Production should add an OpenAI structured-output adapter with SDK parsing, timeout/retry/cost telemetry, then tests, before enabling it.
