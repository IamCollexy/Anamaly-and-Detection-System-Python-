import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Finding, Outcome, Transaction
from app.schemas import InvestigationExplanation, TransactionInput
@dataclass(frozen=True)
class ImportStats: accepted: int=0; rejected: int=0
class ExplanationClient(Protocol):
    """Structural typing: an adapter need not inherit, unlike a typical TS abstract base."""
    async def explain(self, evidence: dict[str,object]) -> InvestigationExplanation: ...
def normalize_record(record: dict[str,object]) -> TransactionInput:
    cleaned={str(k).strip().lower(): v for k,v in record.items()}
    aliases={"reference":"external_reference","customer":"customer_id","type":"transaction_type"}
    return TransactionInput.model_validate({aliases.get(k,k):v for k,v in cleaned.items() if pd.notna(v)})
def csv_chunks(path: str, chunk_size: int=1000):
    """A generator streams a large file rather than holding all frames in memory."""
    yield from pd.read_csv(path, chunksize=chunk_size)
def ingest_csv(session: Session, path: str, job_id: object) -> ImportStats:
    accepted=rejected=0
    for frame in csv_chunks(path):
        for record in frame.drop_duplicates(subset=["provider","external_reference"]).to_dict(orient="records"):
            try:
                item=normalize_record(record)
                with session.begin_nested():
                    session.add(Transaction(**item.model_dump(exclude={"metadata"}), metadata_=item.metadata, import_job_id=job_id)); session.flush()
                accepted+=1
            except Exception: rejected+=1
    return ImportStats(accepted,rejected)
def reconcile(session: Session) -> int:
    groups: dict[str,list[Transaction]]={}
    for tx in session.scalars(select(Transaction)).all():
        if ref:=tx.internal_reference or tx.external_reference: groups.setdefault(ref,[]).append(tx)
    findings=[]
    for ref, group in groups.items():
        amounts={tx.amount for tx in group}; providers={tx.provider for tx in group}
        if len(group)>1 and len(providers)==1: outcome,evidence=Outcome.DUPLICATE,{"reference":ref,"count":len(group)}
        elif len(group)>1 and len(amounts)>1: outcome,evidence=Outcome.MISMATCHED,{"reference":ref,"amounts":[str(x) for x in amounts]}
        elif len(group)==1: outcome,evidence=Outcome.MISSING_FROM_PROVIDER,{"reference":ref}
        else: outcome,evidence=Outcome.MATCHED,{"reference":ref}
        findings.extend(Finding(transaction_id=tx.id,outcome=outcome,evidence=evidence) for tx in group)
    session.add_all(findings); return len(findings)
def detect_anomalies(session: Session, threshold: Decimal=Decimal("100000")) -> int:
    txs=session.scalars(select(Transaction).where(Transaction.amount>=threshold)).all(); session.add_all(Finding(transaction_id=tx.id,outcome=Outcome.SUSPICIOUS,evidence={"rule":"high_amount","threshold":str(threshold)}) for tx in txs); return len(txs)
async def bounded_fetch(delays: list[float], limit: int=5) -> list[float]:
    """Promise.all shape with task, semaphore, timeout and cancellation propagation."""
    sem=asyncio.Semaphore(limit)
    async def one(delay: float) -> float:
        async with sem:
            async with asyncio.timeout(2): await asyncio.sleep(delay); return delay
    return await asyncio.gather(*(asyncio.create_task(one(x)) for x in delays))
