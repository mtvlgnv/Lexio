"""Usage counters and weighted rate-limit logic (Phase 2 extract)."""
import datetime
import ipaddress
from typing import Optional
from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from app.db import SessionLocal
from app.models import User, AnonUsage, SearchLog, UserSearchLog
from app.config import (
    FREE_LOOKUP_LIMIT, ANON_LOOKUP_LIMIT, FREE_OCR_LIMIT, TRIAL_DAYS,
    MODEL_WEIGHTS, HOURLY_LIMIT_PRO, HOURLY_LIMIT_FREE,
    MONTHLY_CREDIT_CAP_PRO, PRO_OCR_MONTHLY_CAP,
)


def _check_hourly_limit(db: DBSession, user: Optional["User"], model: str) -> dict:
    """
    Check whether the user has room in their hourly weighted budget (and, for
    Pro accounts, the monthly credit ceiling) without consuming credits.

    Rolls expired hourly / monthly windows (writes those rolls to the DB) but
    NEVER debits credits — call _consume_hourly_credits() after a successful
    AI response to do that.

    Anonymous users are not subject to either limit — slowapi handles burst
    rate and the monthly free-tier lookup count handles volume.
    """
    weight = MODEL_WEIGHTS.get(model, 1)

    # Anonymous: no per-user limit (slowapi at 20/min already guards bursts)
    if user is None:
        return {"allowed": True, "weight": weight, "used": 0, "limit": -1,
                "reset_in": 0, "month_used": 0, "month_limit": -1}

    u = db.query(User).filter(User.id == user.id).first()
    if u is None:
        return {"allowed": True, "weight": weight, "used": 0, "limit": -1,
                "reset_in": 0, "month_used": 0, "month_limit": -1}

    is_pro    = _is_effectively_pro(u)
    limit     = HOURLY_LIMIT_PRO if is_pro else HOURLY_LIMIT_FREE
    now       = datetime.datetime.utcnow()
    now_month = now.strftime("%Y-%m")

    # ── Hourly window roll ────────────────────────────────────────────────
    rolled = False
    if u.hourly_window_start is None or (now - u.hourly_window_start).total_seconds() >= 3600:
        u.hourly_window_start = now
        u.hourly_weight_used  = 0
        rolled = True

    # ── Monthly credit window roll (Pro only matters) ─────────────────────
    if u.monthly_credit_month != now_month:
        u.monthly_credit_month = now_month
        u.monthly_credit_used  = 0
        rolled = True

    if rolled:
        db.commit()

    hourly_used = u.hourly_weight_used or 0
    month_used  = u.monthly_credit_used or 0

    # Check hourly first (smaller window, more often hit)
    if hourly_used + weight > limit:
        elapsed  = (now - u.hourly_window_start).total_seconds()
        reset_in = max(0, int(3600 - elapsed))
        return {
            "allowed":     False,
            "kind":        "hourly",
            "weight":      weight,
            "used":        hourly_used,
            "limit":       limit,
            "reset_in":    reset_in,
            "month_used":  month_used,
            "month_limit": MONTHLY_CREDIT_CAP_PRO if is_pro else -1,
        }

    # Monthly credit cap (Pro only). Free users are already bounded by the
    # lookup-count cap in _check_usage.
    if is_pro and month_used + weight > MONTHLY_CREDIT_CAP_PRO:
        return {
            "allowed":     False,
            "kind":        "monthly",
            "weight":      weight,
            "used":        hourly_used,
            "limit":       limit,
            "reset_in":    0,
            "month_used":  month_used,
            "month_limit": MONTHLY_CREDIT_CAP_PRO,
        }

    return {
        "allowed":     True,
        "weight":      weight,
        "used":        hourly_used,
        "limit":       limit,
        "reset_in":    max(0, int(3600 - (now - u.hourly_window_start).total_seconds())),
        "month_used":  month_used,
        "month_limit": MONTHLY_CREDIT_CAP_PRO if is_pro else -1,
    }


def _consume_hourly_credits(db: DBSession, user: Optional["User"], model: str) -> dict:
    """
    Debit the user's hourly + monthly credit counters.  Call ONLY after a
    successful AI response is in hand (so failed requests don't cost credits).

    Returns the post-debit values so the caller can echo them in the response.
    """
    weight = MODEL_WEIGHTS.get(model, 1)
    if user is None:
        return {"used": 0, "limit": -1, "weight": weight,
                "month_used": 0, "month_limit": -1, "reset_in": 0}

    u = db.query(User).filter(User.id == user.id).first()
    if u is None:
        return {"used": 0, "limit": -1, "weight": weight,
                "month_used": 0, "month_limit": -1, "reset_in": 0}

    is_pro = _is_effectively_pro(u)
    limit  = HOURLY_LIMIT_PRO if is_pro else HOURLY_LIMIT_FREE
    now    = datetime.datetime.utcnow()

    u.hourly_weight_used = (u.hourly_weight_used or 0) + weight
    if is_pro:
        u.monthly_credit_used = (u.monthly_credit_used or 0) + weight
    db.commit()

    reset_in = max(0, int(3600 - (now - u.hourly_window_start).total_seconds())) \
               if u.hourly_window_start else 0

    return {
        "used":        u.hourly_weight_used,
        "limit":       limit,
        "weight":      weight,
        "reset_in":    reset_in,
        "month_used":  u.monthly_credit_used if is_pro else 0,
        "month_limit": MONTHLY_CREDIT_CAP_PRO if is_pro else -1,
    }

def _read_hourly_status(db: DBSession, user: Optional["User"]) -> dict:
    """Read-only view of the user's current hourly + monthly credit state."""
    if user is None:
        return {"used": 0, "limit": -1, "reset_in": 0,
                "month_used": 0, "month_limit": -1,
                "weights": MODEL_WEIGHTS}
    u = db.query(User).filter(User.id == user.id).first()
    if u is None:
        return {"used": 0, "limit": -1, "reset_in": 0,
                "month_used": 0, "month_limit": -1,
                "weights": MODEL_WEIGHTS}

    is_pro    = _is_effectively_pro(u)
    limit     = HOURLY_LIMIT_PRO if is_pro else HOURLY_LIMIT_FREE
    now       = datetime.datetime.utcnow()
    now_month = now.strftime("%Y-%m")

    if u.hourly_window_start is None or (now - u.hourly_window_start).total_seconds() >= 3600:
        used = 0
        reset_in = 0
    else:
        used = u.hourly_weight_used or 0
        reset_in = max(0, int(3600 - (now - u.hourly_window_start).total_seconds()))

    if is_pro and u.monthly_credit_month == now_month:
        month_used = u.monthly_credit_used or 0
    else:
        month_used = 0

    return {
        "used":        used,
        "limit":       limit,
        "reset_in":    reset_in,
        "month_used":  month_used,
        "month_limit": MONTHLY_CREDIT_CAP_PRO if is_pro else -1,
        "weights":     MODEL_WEIGHTS,
    }

def _is_effectively_pro(u: "User") -> bool:
    """True if the user has a paid Pro plan OR an active trial OR is a member
    of a family plan whose owner is currently Pro."""
    if u.is_pro:
        return True
    if u.trial_expires_at and u.trial_expires_at > datetime.datetime.utcnow():
        return True
    # Family-plan inheritance: this user is a seat on an owner's family plan.
    # Look up the owner's status; if they're Pro, this user is too.
    if u.family_owner_id:
        db = SessionLocal()
        try:
            owner = db.query(User).get(u.family_owner_id)
            if owner and (
                owner.is_pro or
                (owner.trial_expires_at and owner.trial_expires_at > datetime.datetime.utcnow())
            ):
                return True
        finally:
            db.close()
    return False

def _trial_days_left(u: "User") -> int:
    """Days remaining in trial (0 if none/expired)."""
    if u.trial_expires_at and u.trial_expires_at > datetime.datetime.utcnow():
        delta = u.trial_expires_at - datetime.datetime.utcnow()
        return delta.days + (1 if delta.seconds > 0 else 0)
    return 0

def _get_client_ip(request: Request) -> str:
    """Return the real client IP.

    Trust order matters: X-Real-IP is set by our nginx from $remote_addr and
    cannot be forged through it. X-Forwarded-For is client-controllable —
    nginx *appends* the real address, so only the LAST entry is trustworthy;
    taking the first would let anyone spoof their identity (and bypass the
    per-IP rate limits and anonymous free-lookup quota) with a forged header.
    """
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _check_usage(
    db: DBSession,
    user: Optional["User"],
    ip: str,
    kind: str,   # "lookup" | "ocr"
) -> dict:
    """
    Check whether the user has remaining monthly-count quota WITHOUT debiting.
    Rolls expired month windows (and commits those rolls) but never debits.
    Call _consume_usage() after a successful response to debit.

    Returns {"allowed": bool, "used": int, "limit": int}.
    """
    now_month = datetime.datetime.utcnow().strftime("%Y-%m")
    free_limit = FREE_LOOKUP_LIMIT if kind == "lookup" else FREE_OCR_LIMIT

    if user:
        u = db.query(User).filter(User.id == user.id).first()
        is_pro = bool(u and _is_effectively_pro(u))

        # Pro lookups are unbounded at the monthly-count level (hourly/monthly
        # credit caps cover abuse). Pro OCR is capped at PRO_OCR_MONTHLY_CAP.
        if is_pro and kind == "lookup":
            return {"allowed": True, "used": 0, "limit": -1}

        if u:
            rolled = False
            if kind == "lookup":
                if u.lookup_month != now_month:
                    u.monthly_lookups = 0
                    u.lookup_month    = now_month
                    rolled = True
                used  = u.monthly_lookups
                limit = free_limit
            else:
                if u.ocr_month != now_month:
                    u.monthly_ocr = 0
                    u.ocr_month   = now_month
                    rolled = True
                used  = u.monthly_ocr
                limit = PRO_OCR_MONTHLY_CAP if is_pro else free_limit
            if rolled:
                db.commit()
            if used >= limit:
                return {"allowed": False, "used": used, "limit": limit}
            return {"allowed": True, "used": used, "limit": limit}

    # Anonymous — track by IP (always free limits)
    row = db.query(AnonUsage).filter(
        AnonUsage.ip    == ip,
        AnonUsage.month == now_month,
    ).first()
    if not row:
        row = AnonUsage(ip=ip, month=now_month, lookups=0, ocr=0)
        db.add(row)
        db.flush()
        db.commit()

    # Anonymous lookups get a small pre-signup allowance (ANON_LOOKUP_LIMIT);
    # OCR keeps the standard free limit.
    limit = ANON_LOOKUP_LIMIT if kind == "lookup" else FREE_OCR_LIMIT
    used  = row.lookups if kind == "lookup" else row.ocr
    if used >= limit:
        return {"allowed": False, "used": used, "limit": limit}
    return {"allowed": True, "used": used, "limit": limit}


def _consume_usage(
    db: DBSession,
    user: Optional["User"],
    ip: str,
    kind: str,
) -> dict:
    """
    Debit the monthly lookup/OCR counter.  Call ONLY after a successful
    response is in hand.  Returns the post-debit {used, limit}.
    """
    now_month = datetime.datetime.utcnow().strftime("%Y-%m")
    free_limit = FREE_LOOKUP_LIMIT if kind == "lookup" else FREE_OCR_LIMIT

    if user:
        u = db.query(User).filter(User.id == user.id).first()
        is_pro = bool(u and _is_effectively_pro(u))

        if u:
            # Pro lookups are unbounded at the monthly-count level
            if is_pro and kind == "lookup":
                return {"used": 0, "limit": -1}

            if kind == "lookup":
                if u.lookup_month != now_month:
                    u.monthly_lookups = 0
                    u.lookup_month    = now_month
                u.monthly_lookups = (u.monthly_lookups or 0) + 1
                used  = u.monthly_lookups
                limit = free_limit
            else:
                if u.ocr_month != now_month:
                    u.monthly_ocr = 0
                    u.ocr_month   = now_month
                u.monthly_ocr = (u.monthly_ocr or 0) + 1
                used  = u.monthly_ocr
                limit = PRO_OCR_MONTHLY_CAP if is_pro else free_limit
            db.commit()
            return {"used": used, "limit": limit}

    row = db.query(AnonUsage).filter(
        AnonUsage.ip    == ip,
        AnonUsage.month == now_month,
    ).first()
    if not row:
        row = AnonUsage(ip=ip, month=now_month, lookups=0, ocr=0)
        db.add(row)
        db.flush()

    if kind == "lookup":
        row.lookups += 1
        used = row.lookups
    else:
        row.ocr += 1
        used = row.ocr
    db.commit()
    anon_limit = ANON_LOOKUP_LIMIT if kind == "lookup" else FREE_OCR_LIMIT
    return {"used": used, "limit": anon_limit}


def _has_pro_access(db: DBSession, user: Optional["User"]) -> bool:
    """True if a request from `user` is allowed Pro-only models (Balanced/Deep)."""
    if user is None:
        return False
    u = db.query(User).filter(User.id == user.id).first()
    return bool(u and _is_effectively_pro(u))


# ── In-memory cache for top-words (refreshed every hour) ─────────────────────
_top_words_cache: dict = {"data": None, "fetched_at": None}
_CACHE_TTL = datetime.timedelta(hours=1)
