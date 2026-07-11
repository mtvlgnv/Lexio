"""B13: definition feedback (👍/👎) — the prompt-quality dataset."""
import logging

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session as DBSession
from fastapi import Depends

from app.db import get_db
from app.models import DefinitionFeedback
from app.ratelimit import limiter
from app.schemas import FeedbackRequest

logger = logging.getLogger("lexio")
router = APIRouter()


@router.post("/api/feedback")
@limiter.limit("60/minute")
async def submit_feedback(request: Request, req: FeedbackRequest, db: DBSession = Depends(get_db)):
    db.add(DefinitionFeedback(
        word=req.word.strip()[:100],
        model=req.model.strip()[:40],
        verdict=req.verdict,
        lang=req.lang.strip()[:40],
        mode=req.mode,
    ))
    db.commit()
    return {"ok": True}
