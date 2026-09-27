from celery import Celery
from app.config import settings
from app.database import SessionLocal
from app.models import ImportJob, JobStatus
from app.models import Finding
from app.ai import investigate
from app.services import ingest_csv, reconcile
celery_app=Celery("finops",broker=settings.redis_url,backend=settings.redis_url)
celery_app.conf.update(task_always_eager=settings.celery_eager,task_acks_late=True,task_time_limit=300)
@celery_app.task(bind=True,autoretry_for=(OSError,),retry_backoff=True,max_retries=3)
def import_file(self, job_id: str) -> None:
    with SessionLocal() as session:
        job=session.get(ImportJob,job_id)
        if job is None or job.status==JobStatus.COMPLETED: return
        try:
            job.status=JobStatus.PROCESSING; session.commit(); ingest_csv(session,job.source_path,job.id); job.status=JobStatus.COMPLETED; session.commit()
        except Exception as exc:
            session.rollback(); job.status=JobStatus.FAILED; job.error=str(exc); session.commit(); raise
@celery_app.task
def run_reconciliation() -> int:
    with SessionLocal.begin() as session: return reconcile(session)
@celery_app.task(bind=True,autoretry_for=(OSError,),retry_backoff=True,max_retries=2)
def investigate_finding(self, finding_id: str) -> None:
    with SessionLocal() as session:
        finding=session.get(Finding,finding_id)
        if finding is None or finding.ai_explanation is not None: return
        finding.ai_explanation=__import__("asyncio").run(investigate(finding.evidence)).model_dump()
        session.commit()
