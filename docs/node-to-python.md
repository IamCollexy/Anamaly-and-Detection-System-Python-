# Node/NestJS → Python bridge

* **FastAPI dependency functions** are NestJS providers/parameter injection, but a `yield` dependency exposes lifecycle cleanup in ordinary Python.
* **Pydantic** is DTO plus Zod/class-validator-like runtime parsing. Python annotations alone do not validate HTTP/file input.
* **SQLAlchemy 2** is TypeORM/Prisma territory, but a Session is an explicit unit-of-work and SQL expressions are intentionally visible.
* **asyncio** resembles Node async I/O. CPU work blocks an event-loop thread; the GIL means threads generally do not speed pure-Python CPU work. Use processes or Celery for that work.
* **Celery/Redis** is BullMQ-like worker infrastructure: persist a job, publish an id, and process independently of HTTP.
* **uv environments** are isolated interpreter/dependency environments, not literally `node_modules`.
* **pytest fixtures** resemble composable setup dependencies, more than Jest hooks.
