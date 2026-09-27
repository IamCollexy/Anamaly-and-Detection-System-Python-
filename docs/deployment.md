# Deployment paths

Deploy two independently scaled containers: API (`uvicorn`) and worker (`celery`). Run Alembic as a one-off release job before compatible API/worker rollout. Use provider secret stores for `FINOPS_*`, never baked `.env` files. `/health` is liveness; `/ready` verifies PostgreSQL.

## Railway
Build this repository Dockerfile as separate API and worker services, set their commands from `compose.yaml`, attach PostgreSQL/Redis, and use internal connection URLs. Run migrations as a pre-deploy command/job. Inspect service logs and scale workers separately; review current Railway documentation before changing production configuration.

## AWS
Use ECR, ECS Fargate API behind ALB, and a separate Fargate worker. Use RDS PostgreSQL and ElastiCache Redis in private networking; inject Secrets Manager values into task definitions; run migration as a one-off ECS task; send logs to CloudWatch. Scale API on ALB load and workers based on queue monitoring. RDS, ElastiCache, NAT are baseline costs.

## GCP
Use Artifact Registry, Cloud Run API, Cloud SQL PostgreSQL, Memorystore Redis. Host the continuously running Celery worker on GKE or Compute Engine rather than request-driven Cloud Run. Use Secret Manager, Cloud Logging, Cloud SQL connector/private networking, and scale worker replicas on queue depth. Verify current official Cloud Run, Cloud SQL and Memorystore docs before production deployment.
