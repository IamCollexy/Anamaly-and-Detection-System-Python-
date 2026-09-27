"""Probabilistic explanation adapter; deterministic reconciliation stays in services.py."""
import asyncio
import logging
from openai import AsyncOpenAI
from app.config import settings
from app.schemas import InvestigationExplanation

logger=logging.getLogger(__name__)
SYSTEM_PROMPT="""Explain supplied reconciliation evidence. Do not decide an outcome, invent facts, or request secrets."""
async def investigate(evidence: dict[str,object]) -> InvestigationExplanation:
    if not settings.openai_api_key: raise RuntimeError("FINOPS_OPENAI_API_KEY is required for AI investigation")
    client=AsyncOpenAI(api_key=settings.openai_api_key,timeout=15.0,max_retries=2)
    try:
        async with asyncio.timeout(20):
            response=await client.beta.chat.completions.parse(model=settings.openai_model,messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":str(evidence)}],response_format=InvestigationExplanation)
        parsed=response.choices[0].message.parsed
        if parsed is None: raise ValueError("Model returned no structured explanation")
        logger.info("ai_investigation_completed",extra={"model":settings.openai_model,"usage":str(response.usage)})
        return parsed
    finally: await client.close()
