"""Account, usage, annual-recap, OCR, and pro-status routes (Phase 2 extract)."""
import os
import json
import base64
import asyncio
import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession
from google.genai import types as genai_types

from app.db import get_db
from app.models import User, AnonUsage, WordBankEntry, UserSearchLog, SearchLog
from app.security import current_user, optional_user
from app.limits import (
    _get_client_ip, _check_usage, _consume_usage, _has_pro_access,
    _is_effectively_pro, _trial_days_left, _read_hourly_status,
)
from app.ai import openai_client, google_client
from app.ratelimit import limiter
from app.config import (
    FREE_LOOKUP_LIMIT, ANON_LOOKUP_LIMIT, FREE_OCR_LIMIT, PRO_OCR_MONTHLY_CAP,
)

logger = logging.getLogger("lexio")
router = APIRouter()


# ── /api/annual-recap ─────────────────────────────────────────────────────────
# Server-computed reading-year stats: total lookups, languages, top words,
# saved-word count, account age. Designed for the annual subscribers'
# /recap page (a small bonus that makes the annual plan feel qualitatively
# different from monthly).

@router.get("/api/annual-recap")
async def annual_recap(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if not _is_effectively_pro(user):
        raise HTTPException(status_code=402, detail={"code": "pro_required"})

    # Total saved words
    saved_total = db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).count()
    # Saved words by month (last 12)
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=365)
    monthly = {}
    saved_entries = db.query(WordBankEntry).filter(
        WordBankEntry.user_id == user.id,
        WordBankEntry.saved_at >= cutoff,
    ).all()
    for e in saved_entries:
        key = e.saved_at.strftime("%Y-%m") if e.saved_at else "—"
        monthly[key] = monthly.get(key, 0) + 1

    # Top 10 most-recent saved words
    recent = (
        db.query(WordBankEntry)
        .filter(WordBankEntry.user_id == user.id)
        .order_by(WordBankEntry.saved_at.desc())
        .limit(10)
        .all()
    )
    recent_words = [e.word for e in recent]

    # Lifetime lookups via UserSearchLog
    lookup_total = db.query(UserSearchLog).filter(UserSearchLog.user_id == user.id).count()
    lookup_recent = db.query(UserSearchLog).filter(
        UserSearchLog.user_id == user.id,
        UserSearchLog.searched_at >= cutoff,
    ).count()

    # Account age (days since signup)
    age_days = (datetime.datetime.utcnow() - user.created_at).days if user.created_at else 0

    return {
        "saved_total":     saved_total,
        "saved_recent":    sum(monthly.values()),
        "saved_by_month":  monthly,
        "recent_words":    recent_words,
        "lookup_total":    lookup_total,
        "lookup_recent":   lookup_recent,
        "account_age_days": age_days,
        "is_founder":      bool(user.is_founder),
        "plan_interval":   user.subscription_interval,
    }


# ── /ocr ─────────────────────────────────────────────────────────────────────

@router.post("/ocr")
@limiter.limit("5/minute")
async def ocr_image(request: Request, file: UploadFile = File(...),
                    user: Optional[User] = Depends(optional_user),
                    db: DBSession = Depends(get_db)):
    """Extract text from an uploaded image using Gemini or OpenAI vision."""
    # Validate MIME type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Only image files are accepted.")

    # Read and validate size (10 MB max)
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Image must be smaller than 10 MB.")

    ip    = _get_client_ip(request)

    # Pre-flight check (no debit yet)
    usage = _check_usage(db, user, ip, "ocr")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={"code": "limit_exceeded", "kind": "ocr",
                    "used": usage["used"], "limit": usage["limit"]},
        )

    ocr_prompt = (
        "Extract all text visible in this image exactly as it appears. "
        "Preserve paragraph breaks. Return only the extracted text, no commentary."
    )

    # Sync vision SDK calls — run in a thread so the (slow) OCR request
    # doesn't block the event loop for every other request on this worker.
    def _run_ocr() -> str:
        if os.getenv("GOOGLE_API_KEY"):
            response = google_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    genai_types.Part.from_bytes(data=image_bytes, mime_type=file.content_type),
                    ocr_prompt,
                ],
            )
            # response.text can be None when thinking mode produces no text part;
            # fall back to iterating candidates/parts manually
            text = (response.text or "").strip()
            if not text:
                try:
                    parts = response.candidates[0].content.parts
                    text = " ".join(
                        p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)
                    ).strip()
                except Exception:
                    pass
            return text
        elif os.getenv("OPENAI_API_KEY"):
            import base64
            b64 = base64.b64encode(image_bytes).decode()
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                max_tokens=2000,
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{file.content_type};base64,{b64}", "detail": "high"}},
                    {"type": "text", "text": ocr_prompt},
                ]}],
            )
            return response.choices[0].message.content.strip()
        else:
            raise HTTPException(status_code=503, detail="No vision API key configured (GOOGLE_API_KEY or OPENAI_API_KEY required).")

    try:
        text = await asyncio.to_thread(_run_ocr)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("/ocr error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Image processing failed. Please try again.")

    if not text:
        raise HTTPException(status_code=422, detail="No text found in the image.")

    # Debit only after we have valid extracted text
    _consume_usage(db, user, ip, "ocr")

    return {"text": text}


# ── /api/usage ────────────────────────────────────────────────────────────────

@router.get("/api/usage")
async def get_usage(request: Request, user: Optional[User] = Depends(optional_user),
                    db: DBSession = Depends(get_db)):
    """Return current-month usage for the caller (authenticated or anonymous).

    If the request supplied a Bearer token but it was rejected (expired
    token version, pruned JTI, or unknown user), we surface a 401 with a
    machine-readable code so the client can clear stale local state and
    prompt re-login — instead of silently downgrading to anonymous and
    showing the user confusing free-tier limits.
    """
    auth_hdr = request.headers.get("authorization", "")
    if auth_hdr.lower().startswith("bearer ") and user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "session_expired",
                    "message": "Your session ended on this device — please sign in again."},
        )

    now_month = datetime.datetime.utcnow().strftime("%Y-%m")
    ip = _get_client_ip(request)

    hourly_status = _read_hourly_status(db, user)

    if user:
        u = db.query(User).filter(User.id == user.id).first()
        if u and _is_effectively_pro(u):
            pro_ocr = u.monthly_ocr if u.ocr_month == now_month else 0
            return {
                "is_pro": True,
                "lookup": {"used": 0,       "limit": -1},
                "ocr":    {"used": pro_ocr, "limit": PRO_OCR_MONTHLY_CAP},
                "hourly": hourly_status,
            }
        lookups = u.monthly_lookups if u and u.lookup_month == now_month else 0
        ocr     = u.monthly_ocr     if u and u.ocr_month   == now_month else 0
        return {
            "is_pro": False,
            "lookup": {"used": lookups, "limit": FREE_LOOKUP_LIMIT},
            "ocr":    {"used": ocr,     "limit": FREE_OCR_LIMIT},
            "hourly": hourly_status,
        }

    row = db.query(AnonUsage).filter(AnonUsage.ip == ip, AnonUsage.month == now_month).first()
    return {
        "is_pro": False,
        "lookup": {"used": row.lookups if row else 0, "limit": ANON_LOOKUP_LIMIT},
        "ocr":    {"used": row.ocr     if row else 0, "limit": FREE_OCR_LIMIT},
        "hourly": hourly_status,
    }


# ── /api/pro-status ───────────────────────────────────────────────────────────

@router.get("/api/pro-status")
async def pro_status(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    """Return Pro/trial status + subscription metadata for the authenticated user.

    Drives the in-app "Your subscription" card. Keep this lightweight — no
    Stripe API calls; only what we have in the local DB.
    """
    u = db.query(User).filter(User.id == user.id).first()
    # A user is "on trial" if they have a future trial_expires_at — regardless
    # of is_pro, because Stripe-trial users have is_pro=1 set by the
    # subscription webhook.
    trial = bool(u and u.trial_expires_at and u.trial_expires_at > datetime.datetime.utcnow())
    paid  = bool(u and u.is_pro and not trial)
    days  = _trial_days_left(u) if u else 0

    interval     = getattr(u, "subscription_interval", None) if u else None
    is_founder   = bool(getattr(u, "is_founder", 0)) if u else False
    family_role: str | None = None
    family_owner_name: str | None = None
    if u:
        if u.family_owner_id:
            family_role = "member"
            owner = db.query(User).get(u.family_owner_id)
            if owner:
                family_owner_name = (owner.name or owner.email.split("@")[0]) if owner.email else (owner.name or None)
        elif interval == "family":
            family_role = "owner"

    member_since = u.created_at.strftime("%b %Y") if (u and u.created_at) else None

    return {
        "is_pro": paid or trial,
        "is_trial": trial,
        "trial_days_left": days,
        "subscription_interval": interval,    # "month" | "year" | "family" | None
        "is_founder": is_founder,
        "family_role": family_role,           # "owner" | "member" | None
        "family_owner_name": family_owner_name,
        "member_since": member_since,         # "May 2026"
    }
