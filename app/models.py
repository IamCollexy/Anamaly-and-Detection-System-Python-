import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.database import Base

JsonType = JSON().with_variant(JSONB, "postgresql")
class JobStatus(str, enum.Enum): QUEUED="queued"; PROCESSING="processing"; COMPLETED="completed"; FAILED="failed"
class Outcome(str, enum.Enum): MATCHED="matched"; MISMATCHED="mismatched"; MISSING_FROM_PROVIDER="missing_from_provider"; MISSING_INTERNAL="missing_internal"; DUPLICATE="duplicate"; SUSPICIOUS="suspicious"
class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    source_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED)
    error: Mapped[str|None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="import_job")
class Transaction(Base):
    __tablename__="transactions"
    __table_args__=(UniqueConstraint("provider", "external_reference", name="uq_provider_external_reference"), Index("ix_transactions_internal_reference", "internal_reference"), Index("ix_transactions_customer_timestamp", "customer_id", "timestamp"))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    external_reference: Mapped[str|None] = mapped_column(String(128), nullable=True)
    internal_reference: Mapped[str|None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str] = mapped_column(String(64)); amount: Mapped[Decimal] = mapped_column(Numeric(18,2)); currency: Mapped[str] = mapped_column(String(3)); status: Mapped[str] = mapped_column(String(32)); transaction_type: Mapped[str] = mapped_column(String(32)); customer_id: Mapped[str] = mapped_column(String(128)); timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)
    import_job_id: Mapped[UUID|None] = mapped_column(ForeignKey("import_jobs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now()); updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    import_job: Mapped[ImportJob|None] = relationship(back_populates="transactions"); findings: Mapped[list["Finding"]] = relationship(back_populates="transaction")
class Finding(Base):
    __tablename__="findings"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    transaction_id: Mapped[UUID] = mapped_column(ForeignKey("transactions.id"), index=True)
    outcome: Mapped[Outcome] = mapped_column(Enum(Outcome)); evidence: Mapped[dict] = mapped_column(JsonType, default=dict); ai_explanation: Mapped[dict|None] = mapped_column(JsonType, nullable=True)
    transaction: Mapped[Transaction] = relationship(back_populates="findings")
