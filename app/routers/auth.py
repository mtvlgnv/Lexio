"""Authentication, account, OAuth, and public-config routes (Phase 2 extract)."""
import os
import json
import asyncio
import secrets
import datetime
import logging
from typing import Optional

from fastapi import (
    APIRouter, Request, Depends, HTTPException, BackgroundTasks, Header, Response,
)
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as DBSession

from app.db import get_db
from app.models import User, PasswordResetToken
from app.security import (
    current_user, optional_user, hash_password, verify_password, create_token,
    _issue_session_token, _register_session, _revoke_session,
    _decode_token_payload, _jti_is_active, _device_label_from_ua,
)
from app.ratelimit import limiter
from app.schemas import RegisterRequest, LoginRequest

logger = logging.getLogger("lexio")
router = APIRouter()


# ── /auth/register ────────────────────────────────────────────────────────────

@router.post("/auth/register", status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: DBSession = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    # Password registrations are unverified by default IF SMTP is configured
    # (we can actually send the code). Otherwise, gracefully fall back to
    # verified=1 so the user isn't locked out of checkout on dev/preview boxes.
    initial_verified = 0 if (SMTP_USER and SMTP_PASS) else 1
    user = User(
        email          = body.email,
        name           = body.name or body.email.split("@")[0],
        pwd_hash       = hash_password(body.password),
        email_verified = initial_verified,
        # No auto-trial: Pro trial is granted by Stripe Checkout (requires card).
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    # Send verification code immediately if needed (best-effort, non-blocking
    # failures don't break the signup flow — user can resend later).
    if not initial_verified:
        try:
            _issue_email_verification_code(db, user)
        except Exception as exc:
            logger.warning("Failed to send initial verification code: %s", exc)
    # Welcome email — best-effort, never blocks the signup response.
    # Skipped when the account requires verification (the verification email
    # is sent first; welcome goes out after the email is verified instead, but
    # for now we keep it simple and send for verified-on-arrival accounts).
    if initial_verified:
        try:
            _send_welcome_email(user)
        except Exception as exc:
            logger.warning("Failed to send welcome email: %s", exc)
    token = _issue_session_token(db, user, request)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "name": user.name,
                 "email_verified": bool(user.email_verified)},
    }


# ── /auth/login ───────────────────────────────────────────────────────────────

@router.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: DBSession = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.pwd_hash:
        raise HTTPException(status_code=401, detail="This account uses Google sign-in. Please click 'Continue with Google'.")
    if not verify_password(body.password, user.pwd_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    token = _issue_session_token(db, user, request)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "name": user.name,
                 "email_verified": bool(user.email_verified)},
    }


# ── /auth/me ──────────────────────────────────────────────────────────────────

@router.get("/auth/me")
async def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "email_verified": bool(user.email_verified),
    }


# ── /auth/logout ──────────────────────────────────────────────────────────────

@router.post("/auth/logout")
async def logout(
    authorization: Optional[str] = Header(default=None),
    everywhere: bool = False,
    user: User = Depends(current_user),
    db: DBSession = Depends(get_db),
):
    """Sign the user out.

    - Default (`everywhere=false`): only the current device's JWT is
      revoked. Other signed-in devices keep working.
    - `everywhere=true`: bumps token_version, killing every JWT ever
      issued to this account.
    """
    if everywhere:
        db.query(User).filter(User.id == user.id).update({
            User.token_version: (user.token_version or 0) + 1,
            User.active_jtis:   "[]",
        })
        db.commit()
        return {"ok": True, "scope": "everywhere"}

    # Single-device logout: pluck just this jti out of active_jtis
    try:
        payload = _decode_token_payload((authorization or "").split(" ", 1)[1])
        jti     = payload.get("jti")
    except Exception:
        jti = None
    _revoke_session(db, user, jti)
    return {"ok": True, "scope": "this_device"}


# ── /auth/sessions (list active devices) ──────────────────────────────────────

@router.get("/auth/sessions")
async def list_sessions(
    authorization: Optional[str] = Header(default=None),
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    """Return the user's active sessions (devices currently signed in).
    Marks which entry corresponds to the caller's current token."""
    try:
        payload = _decode_token_payload((authorization or "").split(" ", 1)[1])
        current_jti = payload.get("jti")
    except Exception:
        current_jti = None
    try:
        sessions = json.loads(user.active_jtis or "[]")
        if not isinstance(sessions, list):
            sessions = []
    except (json.JSONDecodeError, TypeError):
        sessions = []
    return {
        "max":      MAX_SESSIONS_PER_USER,
        "sessions": [
            {
                "iat":     s.get("iat"),
                "device":  s.get("ua"),
                "current": s.get("jti") == current_jti,
            }
            for s in sessions if isinstance(s, dict)
        ],
    }


# ── /auth/change-password ─────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password:     str = Field(..., min_length=8)

@router.post("/auth/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    user: User = Depends(current_user),
    db: DBSession = Depends(get_db),
):
    """Change password for email/password accounts; invalidates all existing sessions."""
    if not user.pwd_hash:
        raise HTTPException(status_code=400, detail="Password change is not available for social sign-in accounts.")
    if not verify_password(body.current_password, user.pwd_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    new_version = (user.token_version or 0) + 1
    # Reset all active sessions and bump token_version — every previously
    # issued JWT becomes invalid. We then issue a fresh single-session
    # token for the caller so they stay signed in on THIS device.
    db.query(User).filter(User.id == user.id).update({
        User.pwd_hash:      hash_password(body.new_password),
        User.token_version: new_version,
        User.active_jtis:   "[]",
    })
    db.commit()
    db.refresh(user)
    token = _issue_session_token(db, user, request)
    return {"ok": True, "token": token}


# ── /auth/forgot-password & /auth/reset-password ─────────────────────────────

from app.email import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SITE_URL, EMAIL_VERIFY_TTL,
    _send_reset_email, _send_welcome_email, _send_email,
    _send_verification_email, _issue_email_verification_code,
)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

@router.post("/auth/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
):
    # Always return 200 so we don't leak whether an email is registered
    user = db.query(User).filter(User.email == body.email).first()
    if user and user.pwd_hash:
        # Invalidate any existing unused tokens for this user
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == 0,
        ).update({PasswordResetToken.used: 1})
        token = secrets.token_urlsafe(32)
        expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        db.add(PasswordResetToken(user_id=user.id, token=token, expires_at=expires))
        db.commit()
        background_tasks.add_task(_send_reset_email, user.email, token)
    return {"ok": True}

class ResetPasswordRequest(BaseModel):
    token:    str
    password: str = Field(..., min_length=8)

@router.post("/auth/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: DBSession = Depends(get_db),
):
    rec = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == body.token,
        PasswordResetToken.used  == 0,
    ).first()
    if not rec or rec.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    user = db.query(User).filter(User.id == rec.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found.")
    new_version = (user.token_version or 0) + 1
    db.query(User).filter(User.id == user.id).update({
        User.pwd_hash:       hash_password(body.password),
        User.token_version:  new_version,
        User.active_jtis:    "[]",
        # Completing a password reset proves the user owns this email
        # (they received the reset link there) — auto-verify them.
        User.email_verified: 1,
    })
    rec.used = 1
    db.commit()
    db.refresh(user)
    token = _issue_session_token(db, user, request)
    return {"ok": True, "token": token}


# ── /auth/verify-email & /auth/send-verification ─────────────────────────────

class VerifyEmailRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=10)

@router.post("/auth/send-verification")
@limiter.limit("3/minute")
async def send_verification(
    request: Request,
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    """(Re)send a 6-digit email verification code to the caller's address."""
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    if not (SMTP_USER and SMTP_PASS):
        # SMTP not configured — auto-verify the user. This shouldn't happen
        # on production (registration would have already set verified=1),
        # but is a safety net for dev/preview boxes.
        user.email_verified = 1
        db.commit()
        return {"ok": True, "auto_verified": True}
    try:
        _issue_email_verification_code(db, user)
    except RuntimeError:
        # _issue_… already logged; surface a generic error
        raise HTTPException(status_code=503, detail="Could not send verification email — please try again later.")
    return {"ok": True, "sent": True}

@router.post("/auth/verify-email")
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    body: VerifyEmailRequest,
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    """Verify the caller's email address using the 6-digit code sent earlier."""
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    code = (body.code or "").strip()
    if not user.email_verify_code or user.email_verify_code != code:
        raise HTTPException(status_code=400, detail="That code doesn't match. Double-check it or request a new one.")
    if user.email_verify_expires_at and user.email_verify_expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="This code has expired. Request a new one.")
    user.email_verified           = 1
    user.email_verify_code        = None
    user.email_verify_expires_at  = None
    db.commit()
    # First-time verification: send the welcome email now that we know the
    # user owns the address. Best-effort, non-blocking.
    try:
        _send_welcome_email(user)
    except Exception as exc:
        logger.warning("Failed to send welcome email post-verify: %s", exc)
    return {"ok": True}


# ── /auth/account (DELETE) ────────────────────────────────────────────────────

@router.delete("/auth/account", status_code=200)
async def delete_account(
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    """Permanently delete the authenticated user's account and all associated data."""
    uid = user.id
    db.query(UserSearchLog).filter(UserSearchLog.user_id == uid).delete()
    db.query(WordBankEntry).filter(WordBankEntry.user_id == uid).delete()
    db.query(User).filter(User.id == uid).delete()
    db.commit()
    return {"ok": True}


# ── /api/models ───────────────────────────────────────────────────────────────

@router.get("/api/models")
async def get_models():
    """Return available models and their status."""
    return {
        "models": [
            {
                "id": "fast",
                "name": "Fast",
                "provider": "OpenAI",
                "model": "GPT-4o Mini",
                "available": bool(os.getenv("OPENAI_API_KEY")),
                "description": "Quick answers, instant lookups"
            },
            {
                "id": "balanced",
                "name": "Balanced",
                "provider": "Google",
                "model": "Gemini 2.5 Flash",
                "available": bool(os.getenv("GOOGLE_API_KEY")),
                "description": "Smart and thorough, without the wait"
            },
            {
                "id": "deep",
                "name": "Deep",
                "provider": "Anthropic",
                "model": "Claude Sonnet 4.5",
                "available": True,
                "description": "Maximum depth and accuracy"
            }
        ]
    }


@router.get("/api/user-model")
async def get_user_model(
    user:  Optional[User] = Depends(optional_user),
    db:    DBSession       = Depends(get_db),
):
    """Get the user's preferred model."""
    if not user:
        return {"model": "deep"}
    user_record = db.query(User).filter(User.id == user.id).first()
    raw = (user_record.preferred_model if user_record else None) or "deep"
    # Migrate legacy model names to new tiers
    legacy = {"haiku": "fast", "gpt-4-mini": "fast", "gpt-4o-mini": "fast",
               "gemini": "balanced", "sonnet": "deep"}
    return {"model": legacy.get(raw, raw)}


class ModelUpdateRequest(BaseModel):
    model: str = Field(..., max_length=40)


@router.post("/api/user-model")
async def update_user_model(req: ModelUpdateRequest, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    """Update the user's preferred model."""
    valid_models = {"fast", "balanced", "deep"}
    if req.model not in valid_models:
        raise HTTPException(status_code=400, detail=f"Invalid model: {req.model}")

    user_record = db.query(User).filter(User.id == user.id).first()
    if user_record:
        user_record.preferred_model = req.model
        db.commit()
    return {"model": req.model}


# ── /api/config ───────────────────────────────────────────────────────────────

@router.get("/api/config")
async def api_config():
    """Return public client-side configuration (no secrets)."""
    return {
        "google_client_id":  os.getenv("GOOGLE_CLIENT_ID", ""),
        "apple_services_id": os.getenv("APPLE_SERVICES_ID", ""),
        "payhip_url":        os.getenv("PAYHIP_PRODUCT_URL", ""),
    }


from app.oauth import (
    _google_jwks_cache, _GOOGLE_JWKS_TTL, _get_google_jwks, _verify_google_jwt,
)

# ── /auth/google ──────────────────────────────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    credential: str
    nonce: Optional[str] = Field(default=None, max_length=256)

@router.post("/auth/google")
@limiter.limit("10/minute")
async def google_auth(request: Request, body: GoogleAuthRequest, db: DBSession = Depends(get_db)):
    """Verify Google ID token and sign in / register the user."""
    token = body.credential.strip()

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not google_client_id:
        raise HTTPException(status_code=500, detail="Google Sign-In is not configured.")

    try:
        info = await asyncio.to_thread(_verify_google_jwt, token, google_client_id, body.nonce)
    except Exception as exc:
        logger.error("/auth/google local verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Sign-in failed. Please try again.")

    email = info.get("email")
    if not email or not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google account email is not verified.")

    google_sub = info.get("sub")  # stable unique Google user ID
    name       = info.get("name") or email.split("@")[0]

    # Find existing user by email or google_id
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # OAuth signups are verified-by-provider — no need for our own
        # email verification step. No auto-trial: Pro trial is granted
        # by Stripe Checkout (requires card).
        user = User(email=email, name=name, google_id=google_sub,
                    pwd_hash=None, email_verified=1)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Existing account — make sure google_id is set and ensure the
        # account is marked verified (Google has verified the email).
        changed = False
        if not user.google_id:
            user.google_id = google_sub
            changed = True
        if not user.email_verified:
            user.email_verified = 1
            changed = True
        if changed:
            db.commit()

    token = _issue_session_token(db, user, request)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "name": user.name,
                 "email_verified": bool(user.email_verified)},
    }


# ── /auth/apple ───────────────────────────────────────────────────────────────

class AppleAuthRequest(BaseModel):
    id_token:  str
    name: Optional[str] = None   # only sent on very first sign-in

@router.post("/auth/apple")
@limiter.limit("10/minute")
async def apple_auth(request: Request, body: AppleAuthRequest, db: DBSession = Depends(get_db)):
    """Verify Apple id_token (JWT) using Apple's public JWKS and sign in / register the user."""
    import asyncio, urllib.request as _ur, json as _json
    from jose import jwt as _jose_jwt, JWTError as _JWTError

    apple_services_id = os.getenv("APPLE_SERVICES_ID", "")
    if not apple_services_id:
        raise HTTPException(status_code=503, detail="Apple Sign-In is not configured on this server.")

    id_token = body.id_token.strip()

    # Fetch Apple's public JWKS (cached per process is fine — keys rotate rarely)
    def _fetch_jwks():
        with _ur.urlopen("https://appleid.apple.com/auth/keys", timeout=6) as r:
            return _json.loads(r.read())

    try:
        jwks = await asyncio.to_thread(_fetch_jwks)
    except Exception as exc:
        logger.error("/auth/apple key fetch error: %s", exc)
        raise HTTPException(status_code=502, detail="Sign-in failed. Please try again.")

    # Decode header to find the right key
    try:
        header = _jose_jwt.get_unverified_header(id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed Apple token.")

    kid = header.get("kid")
    alg = header.get("alg", "RS256")
    matching_key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not matching_key:
        raise HTTPException(status_code=401, detail="Apple signing key not found.")

    # Verify and decode
    try:
        payload = _jose_jwt.decode(
            id_token,
            matching_key,
            algorithms=[alg],
            audience=apple_services_id,
            issuer="https://appleid.apple.com",
        )
    except _JWTError as exc:
        logger.error("/auth/apple token invalid: %s", exc)
        raise HTTPException(status_code=401, detail="Sign-in failed. Please try again.")

    email    = payload.get("email")
    apple_sub = payload.get("sub")  # stable unique Apple user ID

    if not email and not apple_sub:
        raise HTTPException(status_code=401, detail="Apple token missing user identity.")

    # Apple may hide email — derive a placeholder if missing
    display_email = email or f"{apple_sub}@privaterelay.appleid.com"
    name = body.name or (email.split("@")[0] if email else "Apple User")

    # Find existing user by apple_sub (most reliable) or email
    user = (
        db.query(User).filter(User.google_id == f"apple:{apple_sub}").first()
        or (db.query(User).filter(User.email == display_email).first() if display_email else None)
    )
    if not user:
        # Apple OAuth — provider-verified email. No auto-trial: Pro trial
        # is granted by Stripe Checkout (requires card).
        user = User(email=display_email, name=name,
                    google_id=f"apple:{apple_sub}", pwd_hash=None,
                    email_verified=1)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        changed = False
        if not user.google_id:
            user.google_id = f"apple:{apple_sub}"
            changed = True
        if not user.email_verified:
            user.email_verified = 1
            changed = True
        if changed:
            db.commit()

    token = _issue_session_token(db, user, request)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "name": user.name,
                 "email_verified": bool(user.email_verified)},
    }
