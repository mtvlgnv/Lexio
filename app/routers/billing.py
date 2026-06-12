"""Stripe billing: pricing, checkout, customer portal, webhook (Phase 2 extract)."""
import os
import json
import datetime
import logging
import httpx

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session as DBSession

from app.db import get_db
from app.models import User
from app.security import current_user
from app.limits import _get_client_ip
from app.config import FAMILY_PLAN_SEATS

logger = logging.getLogger("lexio")
router = APIRouter()


# ── Stripe ────────────────────────────────────────────────────────────────────
import stripe as _stripe
import httpx as _httpx

_stripe.api_key          = os.getenv("STRIPE_SECRET_KEY", "")
_STRIPE_WEBHOOK_SECRET   = os.getenv("STRIPE_WEBHOOK_SECRET", "")
_STRIPE_PRICE_ID         = os.getenv("STRIPE_PRICE_ID", "")           # monthly, multi-currency
_STRIPE_PRICE_ID_YEARLY  = os.getenv("STRIPE_PRICE_ID_YEARLY", "")    # annual, multi-currency
_STRIPE_PRICE_ID_FAMILY  = os.getenv("STRIPE_PRICE_ID_FAMILY", "")    # family (4 seats), multi-currency
_SITE_URL                = os.getenv("SITE_URL", "https://lexio.site")

# Statement descriptor (Gap 3) — what appears on the customer's credit card
# statement and Stripe invoices. The full statement descriptor is set on
# the Stripe account itself (Settings → Public details → Statement descriptor),
# but Stripe also lets us tag each invoice with a description that shows up
# in receipts and the customer portal. This makes chargebacks much rarer
# because the charge is unambiguously recognizable as Lexio Pro.
_STRIPE_STATEMENT_DESCRIPTOR_SUFFIX = os.getenv("STRIPE_STATEMENT_DESCRIPTOR_SUFFIX", "PRO")[:22]

# Countries billed in GBP
_GBP_COUNTRIES = {"GB"}
# Countries billed in EUR (eurozone + closely tied currencies)
_EUR_COUNTRIES = {
    "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU",
    "IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES",
    "SE","CH","NO","IS","LI","AL","BA","ME","MK","MD","RS","XK",
}

async def _country_from_ip(ip: str) -> str:
    """Return ISO-3166-1 alpha-2 country code for *ip*, or '' on failure."""
    # Skip private / loopback addresses
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_private or addr.is_loopback:
            return ""
    except ValueError:
        return ""
    try:
        async with _httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "countryCode", "lang": "en"},
            )
            if r.status_code == 200:
                return r.json().get("countryCode", "")
    except Exception:
        pass
    return ""

def _price_for_country(country: str) -> tuple[str, str, str]:
    """Return (currency_code, symbol, monthly_amount) for the visitor's country."""
    if country in _GBP_COUNTRIES:
        return "GBP", "£", "3.99"
    if country in _EUR_COUNTRIES:
        return "EUR", "€", "3.99"
    return "USD", "$", "4.99"


def _yearly_price_for_country(country: str) -> str:
    """Return yearly amount string for the visitor's country.

    Sized for ~33–37% savings vs 12× monthly — the SaaS-standard 'roughly
    2 months free + a touch' that converts well without feeling desperate.
    Below break-even with the existing MONTHLY_CREDIT_CAP_PRO ($33/mo
    absolute worst-case AI cost), so the downside per user is bounded.
    """
    if country in _GBP_COUNTRIES:
        return "31.99"   # £2.66 effective / month — ~33% off 12× £3.99
    if country in _EUR_COUNTRIES:
        return "29.99"   # €2.50 effective / month — ~37% off 12× €3.99
    return "39.99"       # $3.33 effective / month — ~33% off 12× $4.99


def _family_price_for_country(country: str) -> str:
    """Family-plan monthly amount per visitor country. Mirrors the
    multi-currency price object configured in Stripe:
    USD $9.99 / EUR €8.99 / GBP £8.99 (≈ $2.50 per seat on a 4-seat plan)."""
    if country in _GBP_COUNTRIES:
        return "8.99"
    if country in _EUR_COUNTRIES:
        return "8.99"
    return "9.99"


def _format_amount(amount: str, symbol: str) -> str:
    """Render an amount in the locale-appropriate format (EUR uses comma)."""
    if symbol == "€":
        return amount.replace(".", ",")
    return amount


def _savings_percent(monthly_amount: str, yearly_amount: str) -> int:
    """Compute the integer percentage saved on yearly vs 12× monthly."""
    try:
        m = float(monthly_amount.replace(",", "."))
        y = float(yearly_amount.replace(",", "."))
        if m <= 0:
            return 0
        return int(round((1 - (y / (m * 12))) * 100))
    except (TypeError, ValueError):
        return 0


@router.get("/stripe/price-info")
async def stripe_price_info(request: Request):
    """Return both monthly + yearly prices localised to the visitor's
    country. No auth required — this is purely a marketing endpoint."""
    ip = _get_client_ip(request)
    country = await _country_from_ip(ip)
    currency, symbol, monthly_amount = _price_for_country(country)
    yearly_amount = _yearly_price_for_country(country)
    family_amount = _family_price_for_country(country)
    # Localised display strings ("2,99" vs "2.99" in EUR)
    monthly_display = _format_amount(monthly_amount, symbol)
    yearly_display  = _format_amount(yearly_amount,  symbol)
    family_display  = _format_amount(family_amount,  symbol)
    return {
        "currency":              currency,
        "symbol":                symbol,
        # Legacy field — preserved for old cached frontends still in the wild
        "amount":                monthly_display,
        "monthly_amount":        monthly_display,
        "yearly_amount":         yearly_display,
        # Effective monthly cost when paying annually, for display
        "yearly_monthly_equiv":  _format_amount(
            f"{float(yearly_amount.replace(',', '.')) / 12:.2f}", symbol
        ),
        "yearly_savings_pct":    _savings_percent(monthly_amount, yearly_amount),
        "yearly_available":      bool(_STRIPE_PRICE_ID_YEARLY),
        # Family-plan availability: the frontend hides the Family card until
        # STRIPE_PRICE_ID_FAMILY is configured in the server's .env. Lets us
        # ship the infrastructure without exposing an unpriced plan.
        "family_available":      bool(_STRIPE_PRICE_ID_FAMILY),
        "family_amount":         family_display,
        "family_seats":          FAMILY_PLAN_SEATS,
        "country":               country,
    }


@router.post("/stripe/create-checkout")
async def stripe_create_checkout(
    request: Request,
    plan: str = "monthly",
    user: User = Depends(current_user),
):
    """Create a Stripe Checkout session and return its URL.

    Query params:
      plan: "monthly" (default), "yearly", or "family".
    """
    if not _stripe.api_key:
        raise HTTPException(status_code=503, detail="Payments not configured")

    # ── Gap 4: Email verification gate ────────────────────────────────────
    # Subscribers must own the email on file. Without this, abusive users
    # could sign up with a fake email + pay with a real card, then dispute
    # the charge or share the account anonymously. The frontend handles
    # this response code by showing a "verify your email" modal.
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail={
                "error":   "email_not_verified",
                "message": "Please verify your email before subscribing. We'll send you a 6-digit code.",
            },
        )

    # Plan selection. Unknown values fall back to monthly rather than 400ing.
    if plan not in ("monthly", "yearly", "family"):
        plan = "monthly"
    price_id = {
        "monthly": _STRIPE_PRICE_ID,
        "yearly":  _STRIPE_PRICE_ID_YEARLY,
        "family":  _STRIPE_PRICE_ID_FAMILY,
    }[plan]
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Stripe {plan} price not configured",
        )

    ip = _get_client_ip(request)
    country = await _country_from_ip(ip)
    currency, _, _ = _price_for_country(country)

    # Re-use existing Stripe customer if we have one
    customer_kwargs = {}
    if user.stripe_customer_id:
        customer_kwargs["customer"] = user.stripe_customer_id
    else:
        customer_kwargs["customer_email"] = user.email

    # Trial eligibility: users who have never had a Stripe customer record
    # (i.e. never paid and never trialed via Stripe) get TRIAL_DAYS free,
    # but must add a payment method up-front. Stripe charges automatically
    # when the trial ends. Users who've already been Stripe customers
    # (cancelled before, or trial already consumed) check out without a
    # trial. Legacy app-state trialers (trial_expires_at set but no
    # stripe_customer_id) get their NEW 3-day Stripe trial on top — fair,
    # since they would have lost Pro access otherwise.
    is_trial_eligible = not user.stripe_customer_id and not user.is_pro
    plan_label = "annual" if plan == "yearly" else "monthly"
    subscription_data = {
        "metadata":    {"user_id": str(user.id), "plan": plan},
        # Invoice descriptor — what shows on the customer's receipts and
        # in the Stripe customer portal. Clear, recognizable wording cuts
        # accidental chargebacks (Gap 3).
        "description": f"Lexio Pro · {plan_label} subscription",
    }
    if is_trial_eligible:
        subscription_data["trial_period_days"] = TRIAL_DAYS
        # If the user removes their payment method mid-trial, cancel
        # automatically — never let a trial roll over without a card.
        subscription_data["trial_settings"] = {
            "end_behavior": {"missing_payment_method": "cancel"},
        }

    # Stripe's SDK is synchronous — run in a thread to keep the loop free.
    session = await asyncio.to_thread(
        _stripe.checkout.Session.create,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        currency=currency.lower(),
        success_url=f"{_SITE_URL}/?stripe=success&plan={plan}",
        cancel_url=f"{_SITE_URL}/?stripe=cancelled",
        metadata={
            "user_id": str(user.id),
            "plan":    plan,
            "trial":   "1" if is_trial_eligible else "0",
        },
        subscription_data=subscription_data,
        payment_method_collection="always",   # require card even on trial
        allow_promotion_codes=True,
        **customer_kwargs,
    )
    return {"url": session.url, "plan": plan}


@router.post("/stripe/customer-portal")
async def stripe_customer_portal(
    user: User = Depends(current_user),
):
    """Return a Stripe Billing Portal URL so the user can manage / cancel."""
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe subscription found")
    portal = await asyncio.to_thread(
        _stripe.billing_portal.Session.create,
        customer=user.stripe_customer_id,
        return_url=_SITE_URL,
    )
    return {"url": portal.url}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: DBSession = Depends(get_db)):
    """Handle Stripe webhook events (signature-verified)."""
    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")

    try:
        event = _stripe.Webhook.construct_event(payload, sig, _STRIPE_WEBHOOK_SECRET)
    except _stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Convert to plain dict so .get() works across all Stripe SDK versions
    event_dict = event.to_dict()
    etype = event_dict["type"]
    obj   = event_dict["data"]["object"]

    if etype == "checkout.session.completed":
        meta        = obj.get("metadata") or {}
        user_id     = int(meta.get("user_id", 0) or 0)
        customer_id = obj.get("customer")
        if user_id:
            u = db.query(User).filter(User.id == user_id).first()
            if u:
                u.is_pro = 1
                if customer_id:
                    u.stripe_customer_id = customer_id
                db.commit()
                logger.info("Stripe: Pro activated for user %d", user_id)

    elif etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        customer_id = obj.get("customer")
        status      = obj.get("status", "")
        is_active   = status in ("active", "trialing")
        # `trial_end` is a Unix timestamp (or None) when the subscription is trialing
        trial_end   = obj.get("trial_end")
        if customer_id:
            u = db.query(User).filter(User.stripe_customer_id == customer_id).first()
            # Trials created via Checkout: customer may not yet be linked to a
            # local user. Use subscription metadata.user_id as a fallback.
            if u is None:
                meta_uid = (obj.get("metadata") or {}).get("user_id")
                if meta_uid:
                    try:
                        u = db.query(User).filter(User.id == int(meta_uid)).first()
                        if u and not u.stripe_customer_id:
                            u.stripe_customer_id = customer_id
                    except (TypeError, ValueError):
                        u = None
            if u:
                u.is_pro = 1 if is_active else 0
                u.subscription_status = status or None
                # Detect plan tier (monthly / yearly / family) from the price
                # object on the first subscription item. Used to drive the
                # annual-bonus UI and the family-plan invite quota.
                try:
                    items = obj.get("items", {}) or {}
                    data = items.get("data") or []
                    if data:
                        price = data[0].get("price") or {}
                        recurring = price.get("recurring") or {}
                        interval = recurring.get("interval")   # 'month' | 'year'
                        price_id = price.get("id") or ""
                        family_price_id = os.getenv("STRIPE_PRICE_ID_FAMILY", "")
                        if family_price_id and price_id == family_price_id:
                            u.subscription_interval = "family"
                        elif interval in ("month", "year"):
                            u.subscription_interval = interval
                except Exception:
                    pass
                # Persist trial_end so the UI can show "X days left" without
                # round-tripping to Stripe on every page load.
                if status == "trialing" and trial_end:
                    u.trial_expires_at = datetime.datetime.utcfromtimestamp(int(trial_end))
                elif status in ("active",) and u.trial_expires_at and u.trial_expires_at < datetime.datetime.utcnow():
                    # Trial → paid transition: clear stale trial_expires_at
                    u.trial_expires_at = None
                db.commit()
                logger.info(
                    "Stripe: %s status=%s interval=%s → is_pro=%d trial_end=%s for user %d",
                    etype, status, u.subscription_interval, u.is_pro, trial_end, u.id,
                )

    elif etype == "invoice.payment_failed":
        customer_id = obj.get("customer")
        if customer_id:
            u = db.query(User).filter(User.stripe_customer_id == customer_id).first()
            if u:
                logger.warning("Stripe: payment failed for user %d (%s)", u.id, customer_id)
            # Do not revoke immediately — Stripe will retry and send subscription.deleted if truly lapsed

    return {"received": True}
