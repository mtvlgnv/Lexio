"""Transactional email senders + SMTP config (Phase 2 extract)."""
import os
import smtplib
import secrets
import datetime
import logging
from email.mime.text import MIMEText
from sqlalchemy.orm import Session as DBSession

from app.models import User

logger = logging.getLogger("lexio")


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SITE_URL  = os.getenv("SITE_URL", "https://lexio.site")

def _send_reset_email(to_email: str, token: str):
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured — skipping password reset email")
        return
    reset_url = f"{SITE_URL}/reset-password?token={token}"
    body = f"""Hi,

You requested a password reset for your Lexio account.

Click the link below to set a new password (valid for 1 hour):

{reset_url}

If you didn't request this, you can safely ignore this email.

— The Lexio team
"""
    msg = MIMEText(body)
    msg["Subject"] = "Reset your Lexio password"
    msg["From"]    = f"Lexio <{SMTP_USER}>"
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, [to_email], msg.as_string())
    except Exception as exc:
        logger.error("Failed to send reset email to %s: %s", to_email, exc)


# ── Email verification (Gap 4) ───────────────────────────────────────────────
# 6-digit codes, 30-minute TTL. Required for password registrations before
# they can subscribe to Pro. OAuth signups are already provider-verified.
EMAIL_VERIFY_TTL = datetime.timedelta(minutes=30)

def _send_welcome_email(user: "User") -> bool:
    """One-time welcome email sent immediately after registration. Best-effort —
    SMTP failures are silent so they don't break the signup response. Body is
    intentionally short and human so it doesn't read as automated."""
    if not SMTP_USER or not SMTP_PASS:
        return False
    name = (user.name or user.email.split("@")[0]).strip() or "there"
    body = f"""Hi {name},

You just created a Lexio account — welcome.

A few things worth knowing as you start:

  • Paste any text on lexio.site, click a word, and you'll get the
    meaning that fits the sentence around it (not a generic dictionary
    entry).

  • The Chrome extension does the same thing on any page or PDF you
    read in Chrome — right-click a word, choose 'Define with Lexio'.
    https://chromewebstore.google.com/detail/hpongbjknpiflmkokepafpogclldmjob

  • Your free plan gives you 20 contextual lookups a month, Fast mode.
    If you want unlimited + Balanced (Gemini) and Deep (Claude) modes,
    Pro starts a 3-day free trial.

  • Saved words live in your word bank — Pro users get cross-device sync
    and an Anki-ready export.

If anything breaks or you have an idea, write to me directly at
matveylgnv2021@gmail.com. I read every message.

— Matvei
"""
    return _send_email(
        user.email,
        "Welcome to Lexio",
        body,
    )


def _send_email(to_email: str, subject: str, body: str) -> bool:
    """Generic plaintext email send. Returns True on success, False if
    SMTP isn't configured or the send fails. Used by features that don't
    need a templated email (family-plan invites, etc.)."""
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured — skipping email to %s", to_email)
        return False
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = f"Lexio <{SMTP_USER}>"
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


def _send_verification_email(to_email: str, code: str) -> bool:
    """Send a 6-digit verification code. Returns True on success, False if
    SMTP isn't configured or the send fails."""
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured — skipping verification email")
        return False
    body = f"""Hi,

Your Lexio verification code is:

  {code}

The code is valid for 30 minutes. If you didn't sign up for Lexio, you
can safely ignore this email.

— The Lexio team
"""
    msg = MIMEText(body)
    msg["Subject"] = f"Lexio verification code: {code}"
    msg["From"]    = f"Lexio <{SMTP_USER}>"
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as exc:
        logger.error("Failed to send verification email to %s: %s", to_email, exc)
        return False


def _issue_email_verification_code(db: DBSession, user: "User") -> str:
    """Generate a new 6-digit code, persist it, and email it. Returns the
    code so callers can log it in dev. Raises if SMTP isn't configured."""
    code = f"{secrets.randbelow(900000) + 100000:06d}"
    user.email_verify_code       = code
    user.email_verify_expires_at = datetime.datetime.utcnow() + EMAIL_VERIFY_TTL
    db.commit()
    if not _send_verification_email(user.email, code):
        # In environments without SMTP we already mark new users as verified
        # at registration time, so this should never happen on production —
        # but guard anyway to keep the flow non-fatal.
        raise RuntimeError("SMTP not configured")
    return code
