from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models import JobStatus, Outcome
class TransactionInput(BaseModel):
    external_reference: str|None=None; internal_reference: str|None=None; provider: str=Field(min_length=1,max_length=64); amount: Decimal; currency: str=Field(min_length=3,max_length=3); status: str; transaction_type: str; customer_id: str; timestamp: datetime; metadata: dict[str,object]=Field(default_factory=dict)
    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str: return value.upper()
class ImportCreated(BaseModel): id: UUID; status: JobStatus; reused: bool=False
class JobRead(BaseModel): model_config=ConfigDict(from_attributes=True); id: UUID; status: JobStatus; error: str|None
class InvestigationExplanation(BaseModel):
    """The validation firewall between probabilistic model output and persistence."""
    summary: str=Field(max_length=1000); likely_cause: str=Field(max_length=500); evidence: list[str]=Field(max_length=10); recommended_actions: list[str]=Field(max_length=10); confidence: float=Field(ge=0,le=1)
class FindingRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID; transaction_id: UUID; outcome: Outcome; evidence: dict[str,object]; ai_explanation: InvestigationExplanation|None
