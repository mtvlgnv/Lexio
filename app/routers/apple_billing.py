"""Apple In-App Purchase receipt validation — Mac App Store build only.

The desktop app (site.lexio.app, the sandboxed MAS build) purchases Pro via
StoreKit and POSTs its app receipt here. We validate it with Apple's
verifyReceipt endpoint and grant/refresh Pro on the signed-in account — the
same is_pro flag Stripe uses, so Pro stays unified across platforms.

Env: APPLE_SHARED_SECRET — App Store Connect → the app → App Information →
App-Specific Shared Secret. Without it, subscription receipts can't be
validated (status 21004) and this endpoint returns 503.

verifyReceipt is the legacy-but-supported path (App Store Server API with
JWS is the modern one); it's the pragmatic v1: no key management, works for
both sandbox and production receipts, and re-validation on every app launch
plus expiry timestamps covers renewals/cancellations without server
notifications. Expired Apple subscriptions lose is_pro on their next
validation call — or lazily via the expiry column, checked in pro-status.
"""
import datetime
import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.models import User
from app.security import current_user

logger = logging.getLogger("lexio")
router = APIRouter()

DBSession = None
try:  # match the import style of the sibling routers
    from sqlalchemy.orm import Session as DBSession
except Exception:  # pragma: no cover
    pass

_APPLE_SHARED_SECRET = os.getenv("APPLE_SHARED_SECRET", "")
_PROD_URL    = "https://buy.itunes.apple.com/verifyReceipt"
_SANDBOX_URL = "https://sandbox.itunes.apple.com/verifyReceipt"

# Auto-renewable subscription product ids configured in App Store Connect.
_PRODUCT_IDS = {"site.lexio.pro.monthly", "site.lexio.pro.yearly"}


class ReceiptRequest(BaseModel):
    receipt: str = Field(..., min_length=20, max_length=2_000_000)  # base64 app receipt


async def _verify_with_apple(receipt_b64: str) -> dict:
    """POST the receipt to Apple; prod first, sandbox on 21007 (Apple's
    documented flow — a sandbox receipt sent to prod returns 21007)."""
    payload = {
        "receipt-data": receipt_b64,
        "password": _APPLE_SHARED_SECRET,
        "exclude-old-transactions": True,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = (await client.post(_PROD_URL, json=payload)).json()
        if resp.get("status") == 21007:
            resp = (await client.post(_SANDBOX_URL, json=payload)).json()
    return resp


def _latest_subscription(resp: dict):
    """Newest expiry among our subscription products in the receipt.
    Returns (expires_at: datetime | None, original_transaction_id | None)."""
    best_ms, best_otid = 0, None
    for tx in (resp.get("latest_receipt_info") or []):
        if tx.get("product_id") not in _PRODUCT_IDS:
            continue
        try:
            ms = int(tx.get("expires_date_ms", 0))
        except (TypeError, ValueError):
            continue
        if ms > best_ms:
            best_ms, best_otid = ms, tx.get("original_transaction_id")
    if not best_ms:
        return None, None
    return datetime.datetime.utcfromtimestamp(best_ms / 1000), best_otid


@router.post("/apple/verify-receipt")
async def verify_receipt(
    body: ReceiptRequest,
    user: User = Depends(current_user),
    db=Depends(get_db),
):
    if not _APPLE_SHARED_SECRET:
        raise HTTPException(status_code=503, detail="Apple purchases not configured")

    try:
        resp = await _verify_with_apple(body.receipt)
    except Exception as exc:
        logger.warning("verifyReceipt call failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach Apple — try again shortly.")

    status = resp.get("status")
    if status not in (0, 21006):  # 21006 = valid receipt, subscription expired
        logger.warning("verifyReceipt rejected receipt for user %s: status=%s", user.id, status)
        raise HTTPException(status_code=400, detail=f"Apple rejected the receipt (status {status}).")

    expires_at, otid = _latest_subscription(resp)
    now = datetime.datetime.utcnow()
    active = bool(expires_at and expires_at > now)

    # Never let an expired Apple receipt clobber Pro that came from Stripe
    # or a family plan — only touch is_pro when Apple is (or was) the source.
    if active:
        user.is_pro = 1
        user.subscription_status = "active"
        user.subscription_interval = "year" if "yearly" in str(resp) else "month"
        user.apple_original_transaction_id = otid
        user.apple_expires_at = expires_at
    elif user.apple_original_transaction_id and not user.stripe_customer_id and not user.family_owner_id:
        user.is_pro = 0
        user.subscription_status = "canceled"
        user.apple_expires_at = expires_at
    db.commit()

    logger.info("Apple receipt validated for user %s: active=%s expires=%s", user.id, active, expires_at)
    return {
        "is_pro": bool(user.is_pro),
        "source": "apple" if active else None,
        "expires_at": expires_at.isoformat() + "Z" if expires_at else None,
    }
