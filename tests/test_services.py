from datetime import UTC, datetime
from decimal import Decimal
import pytest
from app.schemas import TransactionInput
from app.services import bounded_fetch, normalize_record
@pytest.mark.parametrize("currency",["ngn","USD"])
def test_normalization(currency):
    raw={"provider":"x","amount":"1","currency":currency,"status":"ok","transaction_type":"sale","customer_id":"c","timestamp":"2025-01-01T00:00:00Z"}
    assert normalize_record(raw).currency==currency.upper()
def test_decimal_not_float():
    assert TransactionInput(provider="x",amount="10.20",currency="USD",status="ok",transaction_type="sale",customer_id="c",timestamp=datetime.now(UTC)).amount==Decimal("10.20")
async def test_bounded_fetch(): assert await bounded_fetch([0.001,0.001],limit=1)==[0.001,0.001]
