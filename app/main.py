import shutil
from pathlib import Path
from uuid import UUID
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import settings
from app.database import Base, engine, get_session
from app.models import Finding, ImportJob
from app.schemas import FindingRead, ImportCreated, JobRead
from app.workers import import_file, investigate_finding, run_reconciliation
app=FastAPI(title="FinOps Intelligence",version="0.1.0")
@app.on_event("startup")
def create_tables_for_local_learning() -> None: Base.metadata.create_all(engine); settings.upload_dir.mkdir(parents=True,exist_ok=True)
@app.get("/health")
def health() -> dict[str,str]: return {"status":"ok"}
@app.get("/ready")
def ready(session: Session=Depends(get_session)) -> dict[str,str]: session.execute(text("SELECT 1")); return {"status":"ready"}
@app.post("/imports",response_model=ImportCreated,status_code=202)
def create_import(file: UploadFile=File(...),idempotency_key: str=Header(...,alias="Idempotency-Key"),session: Session=Depends(get_session)) -> ImportCreated:
    if Path(file.filename or "").suffix.lower()!=".csv": raise HTTPException(415,"This first slice accepts CSV; JSON/Excel adapters are next.")
    existing=session.query(ImportJob).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing: return ImportCreated(id=existing.id,status=existing.status,reused=True)
    destination=settings.upload_dir/f"{idempotency_key}.csv"
    with destination.open("wb") as output: shutil.copyfileobj(file.file,output)
    job=ImportJob(idempotency_key=idempotency_key,source_path=str(destination)); session.add(job)
    try: session.commit(); session.refresh(job)
    except IntegrityError: session.rollback(); raise HTTPException(409,"Duplicate idempotency key")
    import_file.delay(str(job.id)); return ImportCreated(id=job.id,status=job.status)
@app.get("/imports/{job_id}",response_model=JobRead)
def get_import(job_id: UUID,session: Session=Depends(get_session)) -> ImportJob:
    if not (job:=session.get(ImportJob,job_id)): raise HTTPException(404,"Import job not found")
    return job
@app.post("/reconciliations",status_code=202)
def queue_reconciliation() -> dict[str,str]: return {"task_id":run_reconciliation.delay().id}
@app.get("/findings",response_model=list[FindingRead])
def list_findings(session: Session=Depends(get_session),limit: int=100,offset: int=0) -> list[Finding]: return session.query(Finding).order_by(Finding.id).offset(offset).limit(min(limit,500)).all()
@app.post("/findings/{finding_id}/investigations",status_code=202)
def queue_investigation(finding_id: UUID,session: Session=Depends(get_session)) -> dict[str,str]:
    if not session.get(Finding,finding_id): raise HTTPException(404,"Finding not found")
    return {"task_id":investigate_finding.delay(str(finding_id)).id}
