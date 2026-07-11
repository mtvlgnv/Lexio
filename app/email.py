"""Transactional email senders + SMTP config (Phase 2 extract)."""
import os
import hmac
import json
import random
import hashlib
import smtplib
import secrets
import datetime
import logging
from email.mime.text import MIMEText
from sqlalchemy.orm import Session as DBSession

from app.models import User, WordBankEntry, UserSearchLog

logger = logging.getLogger("lexio")


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
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
    msg["From"]    = f"Lexio <{SMTP_FROM}>"
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to_email], msg.as_string())
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
    msg["From"]    = f"Lexio <{SMTP_FROM}>"
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to_email], msg.as_string())
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
    msg["From"]    = f"Lexio <{SMTP_FROM}>"
    msg["To"]      = to_email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as exc:
        logger.error("Failed to send verification email to %s: %s", to_email, exc)
        return False


# ── Weekly re-engagement digest (retention) ──────────────────────────────────
# Sent to Pro users with a synced word bank: a handful of words to revisit, in
# the contextual sense Lexio gave them. Free users' banks live only in their
# browser (sync is Pro-gated), so the server has nothing to build from for them.
DIGEST_INTERVAL_DAYS = 7
_DIGEST_WORD_COUNT    = 5

def digest_unsub_token(user_id: int) -> str:
    """Stateless one-click-unsubscribe token. HMAC of the user id under
    SECRET_KEY, so no DB token table is needed and links can't be forged."""
    key = os.getenv("SECRET_KEY", "").encode()
    return hmac.new(key, f"digest:{user_id}".encode(), hashlib.sha256).hexdigest()[:32]

def digest_unsub_token_valid(user_id: int, token: str) -> bool:
    return hmac.compare_digest(digest_unsub_token(user_id), (token or ""))

def _weekly_stats_line(db: DBSession, user: "User") -> str:
    """B17: "N lookups and M new words this week" — the original backlog
    spec's stats framing, folded into the existing word-revisit digest
    rather than shipped as a second competing email. Same current-streak
    algorithm as GET /api/streak in app/routers/account.py (duplicated
    intentionally — that one is a FastAPI route with its own Depends-
    injected session, this runs from a standalone cron script)."""
    now = datetime.datetime.utcnow()
    week_ago = now - datetime.timedelta(days=7)
    lookups_this_week = (
        db.query(UserSearchLog)
        .filter(UserSearchLog.user_id == user.id, UserSearchLog.searched_at >= week_ago)
        .count()
    )
    new_words_this_week = (
        db.query(WordBankEntry)
        .filter(WordBankEntry.user_id == user.id, WordBankEntry.saved_at >= week_ago)
        .count()
    )
    rows = db.query(UserSearchLog.searched_at).filter(UserSearchLog.user_id == user.id).all()
    dayset = {r[0].date() for r in rows if r[0]}
    today = now.date()
    one_day = datetime.timedelta(days=1)
    streak = 0
    cur = today if today in dayset else (today - one_day if (today - one_day) in dayset else None)
    while cur and cur in dayset:
        streak += 1
        cur -= one_day

    parts = [f"{lookups_this_week} lookup{'s' if lookups_this_week != 1 else ''}"]
    if new_words_this_week:
        parts.append(f"{new_words_this_week} new word{'s' if new_words_this_week != 1 else ''} saved")
    line = " and ".join(parts) + " this week"
    if streak >= 2:
        line += f" · {streak}-day streak"
    return line


def _pick_digest_words(db: DBSession, user: "User") -> list[dict]:
    """Return up to _DIGEST_WORD_COUNT parsed word-bank entries, chosen at
    random for variety so repeat digests don't always feature the same words."""
    entries = db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).all()
    parsed = []
    for e in entries:
        try:
            parsed.append(json.loads(e.data))
        except Exception:
            continue
    if len(parsed) > _DIGEST_WORD_COUNT:
        parsed = random.sample(parsed, _DIGEST_WORD_COUNT)
    return parsed

def send_weekly_digest(db: DBSession, user: "User") -> bool:
    """Build and send the weekly word-revisit digest for one user, then stamp
    last_digest_at. Returns False (without stamping) if there's nothing to send
    or SMTP is down, so the user is retried on the next run."""
    if not SMTP_USER or not SMTP_PASS or user.digest_opt_out:
        return False
    words = _pick_digest_words(db, user)
    if len(words) < 3:
        return False
    name = (user.name or user.email.split("@")[0]).strip() or "there"
    lines = []
    for w in words:
        term = (w.get("word") or "").strip()
        # Prefer the contextual sense (Lexio's whole point) over the generic one.
        gloss = (w.get("contextual") or w.get("definition") or "").strip()
        if not term:
            continue
        lines.append(f"  • {term} — {gloss}" if gloss else f"  • {term}")
    unsub_url = f"{SITE_URL}/email/unsubscribe?u={user.id}&t={digest_unsub_token(user.id)}"
    stats_line = _weekly_stats_line(db, user)
    body = f"""Hi {name},

{stats_line}. A few words from your bank, worth a second look:

{chr(10).join(lines)}

Open your word bank to review them all, or paste new text and keep going:
{SITE_URL}/app

— Lexio

—
You're getting this because you save words in Lexio. Don't want the
weekly nudge? Unsubscribe here: {unsub_url}
"""
    ok = _send_email(user.email, "Your words to revisit this week", body)
    if ok:
        user.last_digest_at = datetime.datetime.utcnow()
        db.commit()
    return ok


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
