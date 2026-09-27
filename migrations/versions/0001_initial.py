"""initial schema"""
revision="0001"
down_revision=None
branch_labels=None
depends_on=None
from alembic import op
import sqlalchemy as sa
def upgrade() -> None:
    op.create_table("import_jobs",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("idempotency_key",sa.String(128),nullable=False,unique=True),sa.Column("source_path",sa.String(512),nullable=False),sa.Column("status",sa.Enum("QUEUED","PROCESSING","COMPLETED","FAILED",name="jobstatus"),nullable=False),sa.Column("error",sa.String(1000)),sa.Column("created_at",sa.DateTime(timezone=True)))
    op.create_table("transactions",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("external_reference",sa.String(128)),sa.Column("internal_reference",sa.String(128)),sa.Column("provider",sa.String(64),nullable=False),sa.Column("amount",sa.Numeric(18,2),nullable=False),sa.Column("currency",sa.String(3),nullable=False),sa.Column("status",sa.String(32),nullable=False),sa.Column("transaction_type",sa.String(32),nullable=False),sa.Column("customer_id",sa.String(128),nullable=False),sa.Column("timestamp",sa.DateTime(timezone=True),nullable=False),sa.Column("metadata",sa.JSON(),nullable=False),sa.Column("import_job_id",sa.Uuid(),sa.ForeignKey("import_jobs.id")),sa.UniqueConstraint("provider","external_reference",name="uq_provider_external_reference"))
    op.create_index("ix_transactions_internal_reference","transactions",["internal_reference"]); op.create_index("ix_transactions_customer_timestamp","transactions",["customer_id","timestamp"])
    op.create_table("findings",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("transaction_id",sa.Uuid(),sa.ForeignKey("transactions.id"),nullable=False),sa.Column("outcome",sa.Enum("MATCHED","MISMATCHED","MISSING_FROM_PROVIDER","MISSING_INTERNAL","DUPLICATE","SUSPICIOUS",name="outcome"),nullable=False),sa.Column("evidence",sa.JSON(),nullable=False),sa.Column("ai_explanation",sa.JSON()))
    op.create_index("ix_findings_transaction_id","findings",["transaction_id"])
def downgrade() -> None: op.drop_table("findings"); op.drop_table("transactions"); op.drop_table("import_jobs")
