"""Auth: password hashing, JWT tokens, session tracking, user deps (Phase 2 extract)."""
import os
import json
import secrets
import datetime
from typing import Optional
from fastapi import Request, Header, Depends, HTTPException
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session as DBSession

from app.db import SessionLocal, get_db
from app.models import User


# ── Auth helpers ─────────────────────────────────────────────────────────────

pwd_ctx    = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Add SECRET_KEY=<value> to your .env file. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
ALGORITHM  = "HS256"
TOKEN_TTL  = datetime.timedelta(days=30)


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_token(user_id: int, token_version: int = 0, jti: Optional[str] = None) -> str:
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "exp": datetime.datetime.utcnow() + TOKEN_TTL,
    }
    if jti:
        payload["jti"] = jti
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── Concurrent session management (Gap 1) ────────────────────────────────────
# Cap concurrent active JWTs per user. Friendly enough for real users
# (laptop + phone + tablet + work + chrome-extension = 5+); tight enough
# to make casual account sharing noticeable. The hourly + monthly credit
# caps remain the real cost defenses — this is mostly a visibility/UX
# win and minor abuse friction.
MAX_SESSIONS_PER_USER = 8

def _device_label_from_ua(ua: Optional[str]) -> str:
    """Compact, human-friendly device summary from a User-Agent string."""
    if not ua:
        return "Unknown device"
    ua = ua[:300]  # safety cap
    lo = ua.lower()
    # Browser
    if "edg/" in lo:
        browser = "Edge"
    elif "chrome/" in lo and "chromium" not in lo:
        browser = "Chrome"
    elif "firefox/" in lo:
        browser = "Firefox"
    elif "safari/" in lo and "chrome" not in lo:
        browser = "Safari"
    else:
        browser = "Browser"
    # OS
    if "iphone" in lo:
        os_label = "iPhone"
    elif "ipad" in lo:
        os_label = "iPad"
    elif "android" in lo:
        os_label = "Android"
    elif "mac os x" in lo or "macintosh" in lo:
        os_label = "macOS"
    elif "windows" in lo:
        os_label = "Windows"
    elif "linux" in lo:
        os_label = "Linux"
    else:
        os_label = "Device"
    return f"{browser} on {os_label}"


def _register_session(db: DBSession, user: "User", ua: Optional[str]) -> str:
    """Generate a new jti, register it as the user's session for this device,
    prune to MAX_SESSIONS_PER_USER (oldest dropped first). Returns the jti.

    Re-logging in on the same device REPLACES that device's prior session
    (matched by device label) instead of appending a new one. Without this,
    a user re-running the OAuth flow on one Mac would quietly burn through
    the session cap and evict their phone — which is what happened to the
    founder account before this fix.
    """
    jti = secrets.token_urlsafe(12)
    try:
        sessions = json.loads(user.active_jtis or "[]")
        if not isinstance(sessions, list):
            sessions = []
    except (json.JSONDecodeError, TypeError):
        sessions = []
    ua_label = _device_label_from_ua(ua)
    entry = {
        "jti": jti,
        "iat": datetime.datetime.utcnow().isoformat(timespec="seconds"),
        "ua":  ua_label,
    }
    # Drop any prior session from the same device label (one slot per device
    # class), then newest first, oldest dropped if still over cap.
    sessions = [
        s for s in sessions
        if isinstance(s, dict) and s.get("jti") and s.get("ua") != ua_label
    ]
    sessions = [entry] + sessions
    sessions = sessions[:MAX_SESSIONS_PER_USER]
    user.active_jtis = json.dumps(sessions)
    user.last_login_at = datetime.datetime.utcnow()
    user.last_login_ua = ua_label
    db.commit()
    return jti


def _revoke_session(db: DBSession, user: "User", jti: Optional[str]) -> None:
    """Remove a specific jti from the user's active session list. No-op if
    jti is None (legacy tokens) or not present."""
    if not jti:
        return
    try:
        sessions = json.loads(user.active_jtis or "[]")
        if not isinstance(sessions, list):
            sessions = []
    except (json.JSONDecodeError, TypeError):
        sessions = []
    sessions = [s for s in sessions if isinstance(s, dict) and s.get("jti") != jti]
    user.active_jtis = json.dumps(sessions)
    db.commit()


def _issue_session_token(db: DBSession, user: "User", request: Request) -> str:
    """Convenience: register a new session and return its signed JWT."""
    ua  = request.headers.get("user-agent") if request else None
    jti = _register_session(db, user, ua)
    return create_token(user.id, user.token_version or 0, jti=jti)

def _decode_token_payload(token: str) -> dict:
    """Decode JWT and return the raw payload dict."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def _jti_is_active(user: "User", jti: Optional[str]) -> bool:
    """Return True if `jti` is in the user's active session list, OR the
    token is legacy (no jti) — legacy tokens stay valid until they expire."""
    if not jti:
        return True   # legacy tokens grandfathered (will expire in 30d max)
    try:
        sessions = json.loads(user.active_jtis or "[]")
        if not isinstance(sessions, list):
            return False
    except (json.JSONDecodeError, TypeError):
        return False
    return any(isinstance(s, dict) and s.get("jti") == jti for s in sessions)


def current_user(
    authorization: Optional[str] = Header(default=None),
    db: DBSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token_payload(authorization.split(" ", 1)[1])
    try:
        uid = int(payload["sub"])
        ver = int(payload.get("ver", 0))
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    jti = payload.get("jti")  # may be None for legacy tokens issued pre-session
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if ver != (user.token_version or 0):
        raise HTTPException(status_code=401, detail="Token has been revoked — please sign in again")
    if not _jti_is_active(user, jti):
        raise HTTPException(status_code=401, detail="Session ended on this device — please sign in again")
    return user

def optional_user(
    authorization: Optional[str] = Header(default=None),
    db: DBSession = Depends(get_db),
) -> Optional[User]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = _decode_token_payload(authorization.split(" ", 1)[1])
        uid = int(payload["sub"])
        ver = int(payload.get("ver", 0))
        jti = payload.get("jti")
        user = db.query(User).filter(User.id == uid).first()
        if user and ver == (user.token_version or 0) and _jti_is_active(user, jti):
            return user
        return None
    except HTTPException:
        return None
