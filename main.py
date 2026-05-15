import asyncio
import logging
import os
import json
import secrets
import datetime
import html as _html
import ipaddress
import socket as _socket
import smtplib
from email.mime.text import MIMEText
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends, Header, BackgroundTasks, File, UploadFile, Form
from sqlalchemy import func
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, AnyHttpUrl, EmailStr
import anthropic
import openai
from google import genai as google_genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session as DBSession
from passlib.context import CryptContext
from jose import jwt, JWTError

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lexio")

# ── JSON parsing helpers ──────────────────────────────────────────────────────

def _extract_json_object(text: str) -> str | None:
    """
    Best-effort extraction of the first top-level JSON object from a string.
    Helps when models wrap JSON with prose or code fences.
    """
    if not text:
        return None
    s = text.strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "\"":
                in_str = False
        else:
            if ch == "\"":
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None

def _safe_json_loads(text: str) -> dict:
    """
    Parse model output as JSON. First try strict json.loads; if that fails,
    try extracting a JSON object and parsing that.
    """
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("Model output JSON is not an object")
        return obj
    except Exception:
        extracted = _extract_json_object(text)
        if not extracted:
            raise
        obj = json.loads(extracted)
        if not isinstance(obj, dict):
            raise ValueError("Extracted JSON is not an object")
        return obj

# ── Database ─────────────────────────────────────────────────────────────────

DATABASE_URL = "sqlite:///./lexio.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class User(Base):
    __tablename__ = "users"
    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, nullable=False, index=True)
    name            = Column(String, nullable=True)
    pwd_hash        = Column(String, nullable=True)   # nullable for OAuth-only users
    google_id       = Column(String, nullable=True, index=True)
    preferred_model  = Column(String, default="sonnet", nullable=False)
    is_pro             = Column(Integer, default=0, nullable=False)   # 0=free, 1=pro
    stripe_customer_id = Column(String, nullable=True, index=True)
    monthly_lookups  = Column(Integer, default=0, nullable=False)
    lookup_month     = Column(String, nullable=True)   # "2025-04"
    monthly_ocr      = Column(Integer, default=0, nullable=False)
    ocr_month        = Column(String, nullable=True)
    token_version    = Column(Integer, default=0, nullable=False)   # incremented on logout
    trial_expires_at = Column(DateTime, nullable=True)              # Stripe trial end
    hourly_weight_used  = Column(Integer, default=0, nullable=False)
    hourly_window_start = Column(DateTime, nullable=True)
    monthly_credit_used  = Column(Integer, default=0, nullable=False)
    monthly_credit_month = Column(String, nullable=True)            # "2025-04"
    created_at       = Column(DateTime, default=datetime.datetime.utcnow)

class WordBankEntry(Base):
    __tablename__ = "wordbank"
    id       = Column(Integer, primary_key=True)
    user_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    word     = Column(String, nullable=False)
    data     = Column(Text, nullable=False)   # full JSON blob
    saved_at = Column(DateTime, default=datetime.datetime.utcnow)

class SearchLog(Base):
    """Anonymous search events — no user ID, no context, no IP stored."""
    __tablename__ = "search_log"
    id          = Column(Integer, primary_key=True)
    word        = Column(String, nullable=False, index=True)
    searched_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

class UserSearchLog(Base):
    """Per-user search events for authenticated users."""
    __tablename__ = "user_search_log"
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    word        = Column(String, nullable=False)
    searched_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

class AnonUsage(Base):
    """IP-based usage tracking for anonymous users."""
    __tablename__ = "anon_usage"
    id      = Column(Integer, primary_key=True)
    ip      = Column(String, nullable=False, index=True)
    month   = Column(String, nullable=False, index=True)   # "2025-04"
    lookups = Column(Integer, default=0, nullable=False)
    ocr     = Column(Integer, default=0, nullable=False)

class PasswordResetToken(Base):
    """Single-use password reset tokens, expire after 1 hour."""
    __tablename__ = "password_reset_tokens"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token      = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Integer, default=0, nullable=False)   # 0=unused, 1=used

Base.metadata.create_all(engine)

# ── SQLite migrations ─────────────────────────────────────────────────────────
#
# Each migration is a (version, description, callable) tuple.
# Applied migrations are tracked in the `schema_version` table so each step
# runs exactly once, even when new ones are added in future deploys.

from sqlalchemy import text as _sa_text

def _cols(conn, table: str) -> set:
    """Return the set of column names for *table*."""
    return {row[1] for row in conn.execute(_sa_text(f"PRAGMA table_info({table})"))}

_MIGRATIONS: list[tuple[int, str, object]] = [
    (1, "add google_id", lambda conn, _: (
        conn.execute(_sa_text("ALTER TABLE users ADD COLUMN google_id TEXT"))
        if "google_id" not in _cols(conn, "users") else None
    )),
    (2, "add preferred_model", lambda conn, _: (
        conn.execute(_sa_text("ALTER TABLE users ADD COLUMN preferred_model TEXT DEFAULT 'haiku'"))
        if "preferred_model" not in _cols(conn, "users") else None
    )),
    (3, "add is_pro", lambda conn, _: (
        conn.execute(_sa_text("ALTER TABLE users ADD COLUMN is_pro INTEGER NOT NULL DEFAULT 0"))
        if "is_pro" not in _cols(conn, "users") else None
    )),
    (4, "add monthly_lookups/lookup_month", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("monthly_lookups", "ALTER TABLE users ADD COLUMN monthly_lookups INTEGER NOT NULL DEFAULT 0"),
            ("lookup_month",    "ALTER TABLE users ADD COLUMN lookup_month TEXT"),
        ] if col not in _cols(conn, "users")
    ]),
    (5, "add monthly_ocr/ocr_month", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("monthly_ocr", "ALTER TABLE users ADD COLUMN monthly_ocr INTEGER NOT NULL DEFAULT 0"),
            ("ocr_month",   "ALTER TABLE users ADD COLUMN ocr_month TEXT"),
        ] if col not in _cols(conn, "users")
    ]),
    (6, "create anon_usage table", lambda conn, _: conn.execute(_sa_text("""
        CREATE TABLE IF NOT EXISTS anon_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            month TEXT NOT NULL,
            lookups INTEGER NOT NULL DEFAULT 0,
            ocr INTEGER NOT NULL DEFAULT 0
        )
    """))),
    (7, "add token_version", lambda conn, _: (
        conn.execute(_sa_text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
        if "token_version" not in _cols(conn, "users") else None
    )),
    (8, "create password_reset_tokens table", lambda conn, _: conn.execute(_sa_text("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        )
    """))),
    (9, "add stripe_customer_id", lambda conn, _: (
        conn.execute(_sa_text("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT"))
        if "stripe_customer_id" not in _cols(conn, "users") else None
    )),
    (10, "add trial_expires_at", lambda conn, _: (
        conn.execute(_sa_text("ALTER TABLE users ADD COLUMN trial_expires_at TIMESTAMP"))
        if "trial_expires_at" not in _cols(conn, "users") else None
    )),
    (11, "add hourly rate-limit counters", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("hourly_weight_used",  "ALTER TABLE users ADD COLUMN hourly_weight_used INTEGER NOT NULL DEFAULT 0"),
            ("hourly_window_start", "ALTER TABLE users ADD COLUMN hourly_window_start TIMESTAMP"),
        ] if col not in _cols(conn, "users")
    ]),
    (12, "add monthly Pro credit cap counters", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("monthly_credit_used",  "ALTER TABLE users ADD COLUMN monthly_credit_used INTEGER NOT NULL DEFAULT 0"),
            ("monthly_credit_month", "ALTER TABLE users ADD COLUMN monthly_credit_month TEXT"),
        ] if col not in _cols(conn, "users")
    ]),
]

def _run_migrations():
    with engine.connect() as conn:
        # Ensure the version-tracking table exists
        conn.execute(_sa_text("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
            )
        """))
        conn.commit()

        applied = {row[0] for row in conn.execute(_sa_text("SELECT version FROM schema_version"))}

        for ver, desc, fn in _MIGRATIONS:
            if ver in applied:
                continue
            try:
                fn(conn, ver)
                conn.execute(
                    _sa_text("INSERT INTO schema_version (version, description) VALUES (:v, :d)"),
                    {"v": ver, "d": desc},
                )
                conn.commit()
                logger.info("Migration %d applied: %s", ver, desc)
            except Exception as exc:
                conn.rollback()
                logger.error("Migration %d failed (%s): %s", ver, desc, exc)
                raise

_run_migrations()

# ── Usage limits ─────────────────────────────────────────────────────────────
FREE_LOOKUP_LIMIT = 100
FREE_OCR_LIMIT    = 3
TRIAL_DAYS        = 3

# ── Hourly weighted rate limit ───────────────────────────────────────────────
# Every lookup costs "credits" based on the model used. The weights reflect
# relative compute cost so the limit can't be gamed by spamming Deep mode.
MODEL_WEIGHTS = {"fast": 1, "balanced": 2, "deep": 3}

# Per-hour credit budgets. Pro gets a generous budget that supports very heavy
# reading (≈ 40 Deep / 60 Balanced / 120 Fast lookups per hour) while still
# protecting the service from automated abuse. Free is tighter so a single
# burst can't drain the entire monthly allowance.
HOURLY_LIMIT_PRO  = 120
HOURLY_LIMIT_FREE = 20

# Per-month credit ceiling for Pro accounts. Caps absolute exposure to a single
# abusing account at ~$33/month in Anthropic costs while remaining ~5× more
# than any real reader could ever consume. Free users are already bounded by
# FREE_LOOKUP_LIMIT (100 lookups, fast-only = 100 credits/month).
MONTHLY_CREDIT_CAP_PRO = 20000

# Hard monthly OCR cap for Pro. Realistic heavy use is <100/month; this leaves
# 5× headroom and prevents OCR-spam abuse with GPT-4o vision (~$0.03/scan).
PRO_OCR_MONTHLY_CAP = 500

def _check_hourly_limit(db: DBSession, user: Optional["User"], model: str) -> dict:
    """
    Check (and on success, increment) the user's hourly weighted lookup budget
    AND, for Pro accounts, the monthly credit ceiling.

    Anonymous users are not subject to either — slowapi handles burst rate and
    the monthly free-tier lookup count handles volume.

    Returns:
        {
            "allowed":      bool,
            "weight":       int,    # credits this lookup would cost
            "used":         int,    # credits used this hour (after a successful call)
            "limit":        int,    # hourly budget
            "reset_in":     int,    # seconds until the hourly window resets
            "month_used":   int,    # credits used this month (Pro only; 0 otherwise)
            "month_limit":  int,    # monthly credit cap (Pro only; -1 otherwise)
            "kind":         str,    # only set on denial: "hourly" or "monthly"
        }
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
    if u.hourly_window_start is None or (now - u.hourly_window_start).total_seconds() >= 3600:
        u.hourly_window_start = now
        u.hourly_weight_used  = 0

    # ── Monthly credit window roll (Pro only matters; Free is already capped
    # by lookup count) ────────────────────────────────────────────────────
    if u.monthly_credit_month != now_month:
        u.monthly_credit_month = now_month
        u.monthly_credit_used  = 0

    hourly_used_before = u.hourly_weight_used
    month_used_before  = u.monthly_credit_used or 0

    # Check hourly first (smaller window, more often hit)
    if hourly_used_before + weight > limit:
        elapsed  = (now - u.hourly_window_start).total_seconds()
        reset_in = max(0, int(3600 - elapsed))
        db.commit()
        return {
            "allowed":     False,
            "kind":        "hourly",
            "weight":      weight,
            "used":        hourly_used_before,
            "limit":       limit,
            "reset_in":    reset_in,
            "month_used":  month_used_before,
            "month_limit": MONTHLY_CREDIT_CAP_PRO if is_pro else -1,
        }

    # Monthly credit cap (Pro only). Free users have a separate
    # lookup-count cap enforced in _check_usage.
    if is_pro and month_used_before + weight > MONTHLY_CREDIT_CAP_PRO:
        db.commit()
        return {
            "allowed":     False,
            "kind":        "monthly",
            "weight":      weight,
            "used":        hourly_used_before,
            "limit":       limit,
            "reset_in":    0,
            "month_used":  month_used_before,
            "month_limit": MONTHLY_CREDIT_CAP_PRO,
        }

    u.hourly_weight_used  = hourly_used_before + weight
    if is_pro:
        u.monthly_credit_used = month_used_before + weight
    db.commit()
    return {
        "allowed":     True,
        "weight":      weight,
        "used":        u.hourly_weight_used,
        "limit":       limit,
        "reset_in":    max(0, int(3600 - (now - u.hourly_window_start).total_seconds())),
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
    """True if the user has a paid Pro plan OR an active trial."""
    if u.is_pro:
        return True
    if u.trial_expires_at and u.trial_expires_at > datetime.datetime.utcnow():
        return True
    return False

def _trial_days_left(u: "User") -> int:
    """Days remaining in trial (0 if none/expired)."""
    if u.trial_expires_at and u.trial_expires_at > datetime.datetime.utcnow():
        delta = u.trial_expires_at - datetime.datetime.utcnow()
        return delta.days + (1 if delta.seconds > 0 else 0)
    return 0

def _get_client_ip(request: Request) -> str:
    """Return the real client IP, respecting X-Real-IP from nginx."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def _check_usage(
    db: DBSession,
    user: Optional["User"],
    ip: str,
    kind: str,   # "lookup" | "ocr"
) -> dict:
    """
    Check and (if allowed) increment the usage counter.
    Returns {"allowed": bool, "used": int, "limit": int}.
    """
    now_month = datetime.datetime.utcnow().strftime("%Y-%m")
    free_limit = FREE_LOOKUP_LIMIT if kind == "lookup" else FREE_OCR_LIMIT

    if user:
        u = db.query(User).filter(User.id == user.id).first()
        is_pro = bool(u and _is_effectively_pro(u))

        # Pro lookups are unlimited at the monthly-count level (hourly/monthly
        # credit caps cover them). Pro OCR is capped at PRO_OCR_MONTHLY_CAP to
        # prevent vision-API abuse.
        if is_pro and kind == "lookup":
            return {"allowed": True, "used": 0, "limit": -1}

        if u:
            if kind == "lookup":
                if u.lookup_month != now_month:
                    u.monthly_lookups = 0
                    u.lookup_month    = now_month
                used  = u.monthly_lookups
                limit = free_limit
                if used >= limit:
                    db.commit()
                    return {"allowed": False, "used": used, "limit": limit}
                u.monthly_lookups += 1
            else:
                # OCR: Pro gets PRO_OCR_MONTHLY_CAP, Free gets FREE_OCR_LIMIT
                if u.ocr_month != now_month:
                    u.monthly_ocr = 0
                    u.ocr_month   = now_month
                used  = u.monthly_ocr
                limit = PRO_OCR_MONTHLY_CAP if is_pro else free_limit
                if used >= limit:
                    db.commit()
                    return {"allowed": False, "used": used, "limit": limit}
                u.monthly_ocr += 1
            db.commit()
            return {"allowed": True, "used": used + 1, "limit": limit}

    # Anonymous — track by IP (always free limits)
    row = db.query(AnonUsage).filter(
        AnonUsage.ip    == ip,
        AnonUsage.month == now_month,
    ).first()
    if not row:
        row = AnonUsage(ip=ip, month=now_month, lookups=0, ocr=0)
        db.add(row)
        db.flush()

    limit = free_limit
    if kind == "lookup":
        used = row.lookups
        if used >= limit:
            db.commit()
            return {"allowed": False, "used": used, "limit": limit}
        row.lookups += 1
    else:
        used = row.ocr
        if used >= limit:
            db.commit()
            return {"allowed": False, "used": used, "limit": limit}
        row.ocr += 1

    db.commit()
    return {"allowed": True, "used": used + 1, "limit": limit}


# ── In-memory cache for top-words (refreshed every hour) ─────────────────────
_top_words_cache: dict = {"data": None, "fetched_at": None}
_CACHE_TTL = datetime.timedelta(hours=1)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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

def create_token(user_id: int, token_version: int = 0) -> str:
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "exp": datetime.datetime.utcnow() + TOKEN_TTL,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def _decode_token_payload(token: str) -> dict:
    """Decode JWT and return the raw payload dict."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

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
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if ver != (user.token_version or 0):
        raise HTTPException(status_code=401, detail="Token has been revoked — please sign in again")
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
        user = db.query(User).filter(User.id == uid).first()
        if user and ver == (user.token_version or 0):
            return user
        return None
    except HTTPException:
        return None


# ── Rate limiter ─────────────────────────────────────────────────────────────

limiter = Limiter(key_func=_get_client_ip)
app = FastAPI(title="Lexio")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — wait a moment before looking up another word."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lexio.site"],
    allow_origin_regex=r"chrome-extension://[a-z]{32}",
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── API Clients ──────────────────────────────────────────────────────────────
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
google_client = google_genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))


# ── Request / response models ─────────────────────────────────────────────────

class DefineRequest(BaseModel):
    word:    str = Field(..., min_length=1, max_length=60)
    context: str = Field(..., min_length=1, max_length=8_000)
    lang:    str = Field(default="auto", max_length=40)
    model:   str = Field(default="sonnet", max_length=40)  # haiku, gemini, gpt-4-mini, sonnet

class FetchRequest(BaseModel):
    url: AnyHttpUrl

class RegisterRequest(BaseModel):
    email:    EmailStr
    password: str = Field(..., min_length=8)
    name:     Optional[str] = Field(default=None, max_length=80)

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class WBEntry(BaseModel):
    word:       str = Field(..., min_length=1, max_length=200)
    pos:        Optional[str] = Field(default=None, max_length=100)
    ipa:        Optional[str] = Field(default=None, max_length=200)
    definition: Optional[str] = Field(default=None, max_length=2000)
    contextual: Optional[str] = Field(default=None, max_length=2000)
    why:        Optional[str] = Field(default=None, max_length=1000)
    simpler:    Optional[str] = Field(default=None, max_length=200)
    etymology:  Optional[str] = Field(default=None, max_length=1000)
    register:   Optional[str] = Field(default=None, max_length=100)
    savedAt:    Optional[str] = Field(default=None, max_length=50)
    context:    Optional[str] = Field(default=None, max_length=1000)

    model_config = {"extra": "ignore"}   # silently drop unknown fields

class WBSyncRequest(BaseModel):
    entries: list[WBEntry] = Field(default_factory=list, max_length=500)


# ── Search logging (fire-and-forget, completely anonymous) ────────────────────

def _log_search(word: str) -> None:
    """Write one anonymous row. Normalise to lowercase, skip very short words."""
    w = word.strip().lower()
    if len(w) < 2:
        return
    db = SessionLocal()
    try:
        db.add(SearchLog(word=w))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

def _log_user_search(user_id: int, word: str) -> None:
    """Write one per-user search row."""
    w = word.strip().lower()
    if len(w) < 2:
        return
    db = SessionLocal()
    try:
        db.add(UserSearchLog(user_id=user_id, word=w))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ── Model wrappers ───────────────────────────────────────────────────────────

def _call_anthropic(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """Call Anthropic API and return the response text."""
    message = anthropic_client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _call_openai(prompt: str) -> str:
    """Call OpenAI API (GPT-4 mini) and return the response text."""
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not configured")
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def _call_google(prompt: str) -> str:
    """Call Google Gemini API and return the response text."""
    if not os.getenv("GOOGLE_API_KEY"):
        raise ValueError("GOOGLE_API_KEY not configured")
    response = google_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text.strip()


# ── /define ──────────────────────────────────────────────────────────────────

LANG_NAMES = {
    'en':'English','es':'Spanish','fr':'French','de':'German','it':'Italian',
    'pt':'Portuguese','ru':'Russian','zh':'Chinese','ja':'Japanese','ko':'Korean',
    'ar':'Arabic','hi':'Hindi','nl':'Dutch','pl':'Polish','tr':'Turkish','sv':'Swedish',
}

@app.post("/define")
@limiter.limit("20/minute")
async def define_word(request: Request, req: DefineRequest, bg: BackgroundTasks,
                      user: Optional[User] = Depends(optional_user),
                      db: DBSession = Depends(get_db)):
    ip = _get_client_ip(request)

    # Resolve the requested mode up-front so we can weight the hourly check.
    _model_map = {
        "fast": "fast", "balanced": "balanced", "deep": "deep",
        "haiku": "fast", "gpt-4-mini": "fast", "gpt-4o-mini": "fast",
        "gemini": "balanced", "sonnet": "deep",
    }
    actual_model = _model_map.get((req.model or "deep").lower().strip(), "deep")

    # Hourly + monthly weighted rate limit (per-user; anonymous skipped).
    hourly = _check_hourly_limit(db, user, actual_model)
    if not hourly["allowed"]:
        if hourly.get("kind") == "monthly":
            # Pro monthly credit ceiling — return 402 so the existing limit
            # modal handles it; user has to wait for next billing cycle.
            raise HTTPException(
                status_code=402,
                detail={
                    "code":        "limit_exceeded",
                    "kind":        "monthly_credit",
                    "used":        hourly["month_used"],
                    "limit":       hourly["month_limit"],
                    "weight":      hourly["weight"],
                    "model":       actual_model,
                },
            )
        # Hourly: 429 with Retry-After so clients can back off
        raise HTTPException(
            status_code=429,
            detail={
                "code":     "hourly_limit",
                "weight":   hourly["weight"],
                "used":     hourly["used"],
                "limit":    hourly["limit"],
                "reset_in": hourly["reset_in"],
                "model":    actual_model,
            },
            headers={"Retry-After": str(hourly["reset_in"])},
        )

    usage = _check_usage(db, user, ip, "lookup")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={"code": "limit_exceeded", "kind": "lookup",
                    "used": usage["used"], "limit": usage["limit"]},
        )

    lang_code    = (req.lang or 'auto').strip().lower()
    lang_name    = LANG_NAMES.get(lang_code)   # None if auto/unknown

    # Structural fields (pos, ipa, register, simpler) are always English because
    # they are used as machine-readable labels in the UI.  Semantic fields
    # (definition, contextual, why, etymology) are localised when a language is
    # explicitly chosen, or matched to the input language when lang is 'auto'.
    if lang_name:
        lang_note = (
            f"The semantic fields (definition, contextual, why, etymology) MUST be written entirely in {lang_name}. "
            f"The structural/label fields (pos, ipa, simpler, register) MUST remain in English."
        )
    else:
        lang_note = (
            "Write semantic fields (definition, contextual, why, etymology) in the same language as the input text. "
            "Keep structural/label fields (pos, ipa, simpler, register) in English."
        )

    word_count = len(req.word.strip().split())
    is_phrase   = word_count > 1

    if is_phrase:
        # Phrase / sentence: skip pos & ipa, focus on meaning and usage
        prompt = (
            f'The phrase or sentence "{req.word}" appears in this text: "{req.context}"\n'
            f"{lang_note} Respond ONLY in valid JSON with no markdown:\n"
            '{\"definition\": \"meaning of this phrase/sentence, 1-2 sentences\", '
            '\"contextual\": \"what it specifically means in this passage, 1-2 sentences\", '
            '\"why\": \"why the author chose this phrasing, 1 sentence\", '
            '\"register\": \"exactly one of these English labels: formal, literary, technical, colloquial, neutral, archaic\"}'
        )
        required_keys = ("definition", "contextual")
    else:
        # Single word: full analysis
        prompt = (
            f'The word "{req.word}" appears in this text: "{req.context}"\n'
            f"{lang_note} Respond ONLY in valid JSON with no markdown:\n"
            '{\"pos\": \"English label: noun, verb, adjective, adverb, etc.\", '
            '\"ipa\": \"IPA transcription e.g. /ɪˈfɛm.ər.əl/ — or null if uncertain\", '
            '\"definition\": \"general dictionary definition, 1 sentence\", '
            '\"contextual\": \"definition as used in this passage, 1-2 sentences\", '
            '\"why\": \"why this word rather than a simpler synonym, 1 sentence\", '
            '\"simpler\": \"simplest English one-word synonym, or null if none applies\", '
            '\"etymology\": \"brief word origin, e.g. from Latin ephemeron — or null if uncertain\", '
            '\"register\": \"exactly one of these English labels: formal, literary, technical, colloquial, neutral, archaic\"}'
        )
        required_keys = ("pos", "contextual")

    try:
        # Call the appropriate API
        if actual_model == "fast":
            text = _call_openai(prompt)          # GPT-4o Mini
        elif actual_model == "balanced":
            text = _call_google(prompt)          # Gemini 2.5 Flash
        else:  # deep
            text = _call_anthropic(prompt, "claude-sonnet-4-5-20250929")

        # Clean up markdown code blocks if present
        if text.startswith("```"):
            lines = text.splitlines()
            text  = "\n".join(l for l in lines if not l.startswith("```")).strip()

        result = _safe_json_loads(text)
        for key in required_keys:
            if key not in result:
                raise ValueError(f"Missing key: {key}")

        # Save user's model preference if authenticated
        if user:
            try:
                user_record = db.query(User).filter(User.id == user.id).first()
                if user_record and user_record.preferred_model != actual_model:
                    user_record.preferred_model = actual_model
                    db.commit()
            except Exception:
                db.rollback()

        # Log anonymously (always) and per-user (when authenticated)
        bg.add_task(_log_search, req.word)
        if user:
            bg.add_task(_log_user_search, user.id, req.word)
        return {
            **result,
            "_usage":  {"used": usage["used"], "limit": usage["limit"]},
            "_hourly": {
                "used":        hourly["used"],
                "limit":       hourly["limit"],
                "weight":      hourly["weight"],
                "reset_in":    hourly["reset_in"],
                "month_used":  hourly["month_used"],
                "month_limit": hourly["month_limit"],
            },
        }

    except json.JSONDecodeError as exc:
        logger.error("/define JSON parse error: %s", exc)
        raise HTTPException(status_code=502, detail="The AI model returned an unexpected response. Please try again.")
    except ValueError as exc:
        logger.error("/define value error: %s", exc)
        raise HTTPException(status_code=502, detail="The AI model returned an unexpected response. Please try again.")
    except anthropic.APIError as exc:
        logger.error("/define Anthropic error: %s", exc)
        raise HTTPException(status_code=502, detail="AI provider error. Please try again.")
    except Exception as exc:
        logger.error("/define unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="An unexpected error occurred. Please try again.")


def _ip_is_safe(addr: str) -> bool:
    """Return True only if the IP address is globally routable."""
    try:
        ip = ipaddress.ip_address(addr)
        return (
            ip.is_global
            and not ip.is_private
            and not ip.is_loopback
            and not ip.is_link_local
            and not ip.is_reserved
            and not ip.is_multicast
            and not ip.is_unspecified
        )
    except ValueError:
        return False

def _is_safe_url(url: str) -> bool:
    """
    Return False if any resolved address (IPv4 or IPv6) for the URL's hostname
    is non-global (SSRF guard).  Uses getaddrinfo so all A/AAAA records are
    checked — gethostbyname() only returns a single IPv4 result and misses IPv6.
    """
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return False
        # getaddrinfo returns all A + AAAA records
        results = _socket.getaddrinfo(hostname, None)
        if not results:
            return False
        for res in results:
            addr = res[4][0]
            if not _ip_is_safe(addr):
                return False
        return True
    except Exception:
        return False


def _safe_fetch(url: str, max_redirects: int = 3) -> str | None:
    """
    Fetch *url* with a redirect-following loop that re-checks SSRF safety on
    every hop.  Returns the raw HTML/text or None on failure.
    """
    import urllib.request as _ur
    import urllib.error as _ue

    current_url = url
    for _ in range(max_redirects + 1):
        if not _is_safe_url(current_url):
            return None
        req = _ur.Request(
            current_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Lexio/1.0; +https://lexio.site)"},
        )
        try:
            with _ur.urlopen(req, timeout=10) as resp:
                # Follow redirect manually so we can re-check the destination
                final_url = resp.geturl()
                if final_url != current_url:
                    current_url = final_url
                    continue
                content_type = resp.headers.get_content_type() or ""
                if not any(t in content_type for t in ("html", "text", "xml")):
                    return None
                return resp.read(2_000_000).decode("utf-8", errors="replace")
        except _ue.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                from urllib.parse import urljoin
                current_url = urljoin(current_url, exc.headers["Location"])
                continue
            return None
    return None   # too many redirects


# ── /fetch-text ───────────────────────────────────────────────────────────────

@app.post("/fetch-text")
@limiter.limit("5/minute")
async def fetch_article(request: Request, payload: FetchRequest):
    try:
        import trafilatura
        url = str(payload.url)

        if not _is_safe_url(url):
            raise HTTPException(status_code=422, detail="URL not allowed.")

        def _extract() -> str | None:
            html_content = _safe_fetch(url)
            if not html_content:
                return None
            return trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )

        text = await asyncio.to_thread(_extract)
        if not text or len(text.strip()) < 50:
            raise HTTPException(
                status_code=422,
                detail="Could not extract readable text — try copying and pasting the article manually.",
            )
        return {"text": text[:8_000].strip()}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("/fetch-text error: %s", exc)
        raise HTTPException(status_code=422, detail="Could not extract text from that URL.")


# ── /stats/top-words ─────────────────────────────────────────────────────────

@app.get("/stats/top-words")
async def top_words(db: DBSession = Depends(get_db)):
    """
    Return the top 5 most-looked-up words in the current calendar month.
    Result is cached in memory for 1 hour so the DB isn't queried on every
    page load.
    """
    now = datetime.datetime.utcnow()

    # Serve from cache if still fresh
    if (
        _top_words_cache["data"] is not None
        and _top_words_cache["fetched_at"] is not None
        and now - _top_words_cache["fetched_at"] < _CACHE_TTL
    ):
        return _top_words_cache["data"]

    # Start of current month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rows = (
        db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .filter(SearchLog.searched_at >= month_start)
        .group_by(SearchLog.word)
        .order_by(func.count(SearchLog.id).desc())
        .limit(5)
        .all()
    )

    result = {
        "month": now.strftime("%B %Y"),
        "words": [{"word": r.word, "count": r.n} for r in rows],
    }

    _top_words_cache["data"]       = result
    _top_words_cache["fetched_at"] = now
    return result


# ── /auth/register ────────────────────────────────────────────────────────────

@app.post("/auth/register", status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: DBSession = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(
        email    = body.email,
        name     = body.name or body.email.split("@")[0],
        pwd_hash = hash_password(body.password),
        # No auto-trial: Pro trial is granted by Stripe Checkout (requires card).
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id, user.token_version or 0), "user": {"id": user.id, "email": user.email, "name": user.name}}


# ── /auth/login ───────────────────────────────────────────────────────────────

@app.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: DBSession = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.pwd_hash:
        raise HTTPException(status_code=401, detail="This account uses Google sign-in. Please click 'Continue with Google'.")
    if not verify_password(body.password, user.pwd_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"token": create_token(user.id, user.token_version or 0), "user": {"id": user.id, "email": user.email, "name": user.name}}


# ── /auth/me ──────────────────────────────────────────────────────────────────

@app.get("/auth/me")
async def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}


# ── /auth/logout ──────────────────────────────────────────────────────────────

@app.post("/auth/logout")
async def logout(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    """Invalidate all existing tokens for this user by bumping token_version."""
    db.query(User).filter(User.id == user.id).update(
        {User.token_version: (user.token_version or 0) + 1}
    )
    db.commit()
    return {"ok": True}


# ── /auth/change-password ─────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password:     str = Field(..., min_length=8)

@app.post("/auth/change-password")
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
    db.query(User).filter(User.id == user.id).update({
        User.pwd_hash:      hash_password(body.new_password),
        User.token_version: new_version,
    })
    db.commit()
    # Return a fresh token so the caller stays logged in
    return {"ok": True, "token": create_token(user.id, new_version)}


# ── /auth/forgot-password & /auth/reset-password ─────────────────────────────

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

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

@app.post("/auth/forgot-password")
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

@app.post("/auth/reset-password")
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
        User.pwd_hash:      hash_password(body.password),
        User.token_version: new_version,
    })
    rec.used = 1
    db.commit()
    return {"ok": True, "token": create_token(user.id, new_version)}


# ── /auth/account (DELETE) ────────────────────────────────────────────────────

@app.delete("/auth/account", status_code=200)
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

@app.get("/api/models")
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


@app.get("/api/user-model")
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


@app.post("/api/user-model")
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

@app.get("/api/config")
async def api_config():
    """Return public client-side configuration (no secrets)."""
    return {
        "google_client_id":  os.getenv("GOOGLE_CLIENT_ID", ""),
        "apple_services_id": os.getenv("APPLE_SERVICES_ID", ""),
        "payhip_url":        os.getenv("PAYHIP_PRODUCT_URL", ""),
    }


_google_jwks_cache: dict = {"keys": None, "fetched_at": None}
_GOOGLE_JWKS_TTL = datetime.timedelta(hours=6)

def _get_google_jwks() -> list:
    now = datetime.datetime.utcnow()
    if (
        _google_jwks_cache["keys"] is not None
        and _google_jwks_cache["fetched_at"] is not None
        and now - _google_jwks_cache["fetched_at"] < _GOOGLE_JWKS_TTL
    ):
        return _google_jwks_cache["keys"]
    import urllib.request as _ur2
    import json as _json
    with _ur2.urlopen("https://www.googleapis.com/oauth2/v3/certs", timeout=8) as r:
        data = _json.loads(r.read())
    _google_jwks_cache["keys"] = data.get("keys", [])
    _google_jwks_cache["fetched_at"] = now
    return _google_jwks_cache["keys"]

def _verify_google_jwt(token: str, client_id: str, expected_nonce: Optional[str] = None) -> dict:
    """
    Verify Google ID token locally using cached JWKS.
    If *expected_nonce* is provided it must match the nonce claim in the token.
    """
    from jose import jwt as jose_jwt, JWTError as _JWTErr
    from jose.exceptions import ExpiredSignatureError, JWTClaimsError

    try:
        header = jose_jwt.get_unverified_header(token)
    except Exception:
        raise ValueError("Malformed token header")

    kid = header.get("kid")
    keys = _get_google_jwks()
    key  = next((k for k in keys if k.get("kid") == kid), None)

    # If kid not found, refresh cache once and retry
    if key is None:
        _google_jwks_cache["fetched_at"] = None
        keys = _get_google_jwks()
        key  = next((k for k in keys if k.get("kid") == kid), None)

    if key is None:
        raise ValueError("Google public key not found")

    claims = jose_jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=client_id,
    )

    issuer = claims.get("iss", "")
    if issuer not in ("https://accounts.google.com", "accounts.google.com"):
        raise ValueError("Invalid token issuer")

    # Nonce binding: reject the token if the caller supplied a nonce and it doesn't match
    if expected_nonce is not None:
        token_nonce = claims.get("nonce", "")
        if not token_nonce or token_nonce != expected_nonce:
            raise ValueError("Nonce mismatch — possible replay attack")

    return claims


# ── /auth/google ──────────────────────────────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    credential: str
    nonce: Optional[str] = Field(default=None, max_length=256)

@app.post("/auth/google")
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
        # No auto-trial: Pro trial is granted by Stripe Checkout (requires card).
        user = User(email=email, name=name, google_id=google_sub, pwd_hash=None)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.google_id:
            user.google_id = google_sub
            db.commit()

    return {"token": create_token(user.id, user.token_version or 0), "user": {"id": user.id, "email": user.email, "name": user.name}}


# ── /auth/apple ───────────────────────────────────────────────────────────────

class AppleAuthRequest(BaseModel):
    id_token:  str
    name: Optional[str] = None   # only sent on very first sign-in

@app.post("/auth/apple")
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
        # No auto-trial: Pro trial is granted by Stripe Checkout (requires card).
        user = User(email=display_email, name=name, google_id=f"apple:{apple_sub}", pwd_hash=None)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.google_id:
            user.google_id = f"apple:{apple_sub}"
            db.commit()

    return {"token": create_token(user.id, user.token_version or 0), "user": {"id": user.id, "email": user.email, "name": user.name}}


# ── /wordbank/sync ────────────────────────────────────────────────────────────
# Client sends its full local word bank; server merges and returns the union.

@app.post("/wordbank/sync")
async def sync_wordbank(
    body: WBSyncRequest,
    user: User = Depends(current_user),
    db:   DBSession = Depends(get_db),
):
    # Index existing server entries by word (case-insensitive)
    existing = {
        e.word.lower(): e
        for e in db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).all()
    }

    # Upsert client entries
    for entry in body.entries:
        word = entry.word.strip()
        if not word:
            continue
        key = word.lower()
        entry_dict = entry.model_dump(exclude_none=True)
        if key in existing:
            existing[key].data = json.dumps(entry_dict)
        else:
            new_entry = WordBankEntry(
                user_id = user.id,
                word    = word,
                data    = json.dumps(entry_dict),
            )
            db.add(new_entry)
            existing[key] = new_entry

    db.commit()

    # Return the full server word bank to the client
    all_entries = db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).all()
    return {"entries": [json.loads(e.data) for e in all_entries]}


# ── /wordbank ─────────────────────────────────────────────────────────────────

@app.get("/wordbank")
async def get_wordbank(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    entries = db.query(WordBankEntry).filter(WordBankEntry.user_id == user.id).all()
    return {"entries": [json.loads(e.data) for e in entries]}


@app.delete("/wordbank/{word}")
async def delete_word(word: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    entry = db.query(WordBankEntry).filter(
        WordBankEntry.user_id == user.id,
        WordBankEntry.word    == word,
    ).first()
    if entry:
        db.delete(entry)
        db.commit()
    return {"ok": True}


# ── /api/admin/* ──────────────────────────────────────────────────────────────

_START_TIME = datetime.datetime.utcnow()

def _check_admin(x_admin_key: Optional[str] = Header(default=None)):
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden")

@app.get("/api/admin/health")
async def admin_health(db: DBSession = Depends(get_db), _=Depends(_check_admin)):
    """Server health snapshot."""
    # DB ping
    db_ok = False
    try:
        db.execute(__import__('sqlalchemy').text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    # Disk usage
    stat = os.statvfs("/")
    disk_total = stat.f_blocks * stat.f_frsize
    disk_free  = stat.f_bfree  * stat.f_frsize
    disk_used  = disk_total - disk_free

    uptime_secs = int((datetime.datetime.utcnow() - _START_TIME).total_seconds())

    return {
        "status":      "ok" if db_ok else "degraded",
        "db":          db_ok,
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "google_oauth_set":  bool(os.getenv("GOOGLE_CLIENT_ID")),
        "uptime_seconds":    uptime_secs,
        "disk": {
            "total_gb": round(disk_total / 1e9, 2),
            "used_gb":  round(disk_used  / 1e9, 2),
            "free_gb":  round(disk_free  / 1e9, 2),
            "pct_used": round(disk_used  / disk_total * 100, 1),
        },
        "server_time": datetime.datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/admin/stats")
async def admin_stats(db: DBSession = Depends(get_db), _=Depends(_check_admin)):
    """Full statistics snapshot for the admin dashboard."""
    now   = datetime.datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - datetime.timedelta(days=7)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ── Users ────────────────────────────────────────────────────────
    total_users   = db.query(func.count(User.id)).scalar()
    users_today   = db.query(func.count(User.id)).filter(User.created_at >= today).scalar()
    users_week    = db.query(func.count(User.id)).filter(User.created_at >= week).scalar()
    users_month   = db.query(func.count(User.id)).filter(User.created_at >= month).scalar()
    oauth_users   = db.query(func.count(User.id)).filter(User.google_id != None).scalar()
    pwd_users     = db.query(func.count(User.id)).filter(User.pwd_hash != None, User.pwd_hash != "").scalar()

    # ── Word bank ────────────────────────────────────────────────────
    total_wb      = db.query(func.count(WordBankEntry.id)).scalar()
    wb_today      = db.query(func.count(WordBankEntry.id)).filter(WordBankEntry.saved_at >= today).scalar()

    # ── Searches ─────────────────────────────────────────────────────
    total_searches  = db.query(func.count(SearchLog.id)).scalar()
    searches_today  = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= today).scalar()
    searches_week   = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= week).scalar()
    searches_month  = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= month).scalar()

    # ── Top words all-time ────────────────────────────────────────────
    top_all = (
        db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .group_by(SearchLog.word)
        .order_by(func.count(SearchLog.id).desc())
        .limit(10)
        .all()
    )

    # ── Top words this month ──────────────────────────────────────────
    top_month = (
        db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .filter(SearchLog.searched_at >= month)
        .group_by(SearchLog.word)
        .order_by(func.count(SearchLog.id).desc())
        .limit(10)
        .all()
    )

    # ── Searches per day (last 30 days) ───────────────────────────────
    thirty_ago = today - datetime.timedelta(days=29)
    daily_rows = (
        db.query(
            func.date(SearchLog.searched_at).label("day"),
            func.count(SearchLog.id).label("n"),
        )
        .filter(SearchLog.searched_at >= thirty_ago)
        .group_by(func.date(SearchLog.searched_at))
        .order_by(func.date(SearchLog.searched_at))
        .all()
    )
    # Fill in missing days with 0
    daily_map = {r.day: r.n for r in daily_rows}
    daily_searches = []
    for i in range(30):
        d = (thirty_ago + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        daily_searches.append({"date": d, "count": daily_map.get(d, 0)})

    # ── New users per day (last 30 days) ──────────────────────────────
    user_rows = (
        db.query(
            func.date(User.created_at).label("day"),
            func.count(User.id).label("n"),
        )
        .filter(User.created_at >= thirty_ago)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )
    user_map = {r.day: r.n for r in user_rows}
    daily_users = []
    for i in range(30):
        d = (thirty_ago + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        daily_users.append({"date": d, "count": user_map.get(d, 0)})

    # ── Recent sign-ups ───────────────────────────────────────────────
    recent_users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "users": {
            "total":  total_users,
            "today":  users_today,
            "week":   users_week,
            "month":  users_month,
            "oauth":  oauth_users,
            "password": pwd_users,
        },
        "wordbank": {
            "total": total_wb,
            "today": wb_today,
        },
        "searches": {
            "total": total_searches,
            "today": searches_today,
            "week":  searches_week,
            "month": searches_month,
        },
        "top_words_alltime": [{"word": r.word, "count": r.n} for r in top_all],
        "top_words_month":   [{"word": r.word, "count": r.n} for r in top_month],
        "daily_searches":    daily_searches,
        "daily_users":       daily_users,
        "recent_users": [
            {
                "id":         u.id,
                "email":      u.email,
                "name":       u.name,
                "auth":       "oauth" if u.google_id else "password",
                "created_at": u.created_at.isoformat() + "Z" if u.created_at else None,
            }
            for u in recent_users
        ],
        "generated_at": now.isoformat() + "Z",
    }


def _make_admin_cookie() -> str:
    payload = {
        "admin": True,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=8),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def _verify_admin_cookie(request: Request) -> bool:
    token = request.cookies.get("admin_sess", "")
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return data.get("admin") is True
    except Exception:
        return False


# ── /admin  (server-side rendered, no JS required) ───────────────────────────

_LOGIN_FORM_TMPL = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lexio Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#f5f4f0;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border:1px solid #ddd;border-radius:12px;padding:36px;width:340px;box-shadow:0 4px 20px rgba(0,0,0,.08)}
h1{font-size:1.2rem;margin-bottom:6px}p{font-size:.82rem;color:#777;margin-bottom:18px}
input{width:100%;padding:9px 12px;border:1px solid #ddd;border-radius:8px;font-size:.9rem;margin-bottom:10px}
button{width:100%;padding:10px;background:#c47028;color:#fff;border:none;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer}
.err{color:#c00;font-size:.8rem;margin-top:8px}
</style></head><body>
<div class="box">
  <h1>Lexio Admin</h1><p>Enter your admin key to view the dashboard.</p>
  <form method="post" action="/admin">
    <input name="key" type="password" placeholder="Admin key" autofocus>
    <button type="submit">Access dashboard</button>
  </form>
  {error}
</div></body></html>"""

@app.post("/admin", response_class=HTMLResponse)
@app.post("/admin/", response_class=HTMLResponse)
async def admin_login(request: Request, key: str = Form(...)):
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or key != admin_key:
        error_html = _LOGIN_FORM_TMPL.replace("{error}", '<p class="err">Wrong key.</p>')
        return HTMLResponse(error_html, status_code=401)
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie("admin_sess", _make_admin_cookie(),
                    httponly=True, secure=True, samesite="strict", max_age=28800)
    return resp


@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
async def admin_page(request: Request, db: DBSession = Depends(get_db)):
    if not _verify_admin_cookie(request):
        return HTMLResponse(_LOGIN_FORM_TMPL.replace("{error}", ""))

    # ── Gather all stats ──────────────────────────────────────────────────────
    now   = datetime.datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - datetime.timedelta(days=7)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users  = db.query(func.count(User.id)).scalar() or 0
    users_today  = db.query(func.count(User.id)).filter(User.created_at >= today).scalar() or 0
    users_week   = db.query(func.count(User.id)).filter(User.created_at >= week).scalar() or 0
    users_month  = db.query(func.count(User.id)).filter(User.created_at >= month).scalar() or 0
    oauth_users  = db.query(func.count(User.id)).filter(User.google_id != None).scalar() or 0
    pwd_users    = db.query(func.count(User.id)).filter(User.pwd_hash != None, User.pwd_hash != "").scalar() or 0

    total_wb     = db.query(func.count(WordBankEntry.id)).scalar() or 0
    wb_today     = db.query(func.count(WordBankEntry.id)).filter(WordBankEntry.saved_at >= today).scalar() or 0

    total_searches  = db.query(func.count(SearchLog.id)).scalar() or 0
    searches_today  = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= today).scalar() or 0
    searches_week   = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= week).scalar() or 0
    searches_month  = db.query(func.count(SearchLog.id)).filter(SearchLog.searched_at >= month).scalar() or 0

    top_month_rows = (db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .filter(SearchLog.searched_at >= month).group_by(SearchLog.word)
        .order_by(func.count(SearchLog.id).desc()).limit(10).all())
    top_all_rows = (db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .group_by(SearchLog.word).order_by(func.count(SearchLog.id).desc()).limit(10).all())

    thirty_ago = today - datetime.timedelta(days=29)
    daily_search_rows = (db.query(func.date(SearchLog.searched_at).label("day"), func.count(SearchLog.id).label("n"))
        .filter(SearchLog.searched_at >= thirty_ago).group_by(func.date(SearchLog.searched_at)).all())
    daily_user_rows = (db.query(func.date(User.created_at).label("day"), func.count(User.id).label("n"))
        .filter(User.created_at >= thirty_ago).group_by(func.date(User.created_at)).all())

    search_map = {r.day: r.n for r in daily_search_rows}
    user_map   = {r.day: r.n for r in daily_user_rows}

    def sparkline(data_map, color):
        days  = [(thirty_ago + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
        vals  = [data_map.get(d, 0) for d in days]
        maxv  = max(vals) if vals else 1
        maxv  = maxv or 1
        W, H, pl, pr, pt, pb = 500, 100, 8, 8, 6, 18
        cW, cH = W - pl - pr, H - pt - pb
        def px(i): return pl + (i / (len(vals) - 1)) * cW if len(vals) > 1 else pl
        def py(v): return pt + cH - (v / maxv) * cH
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals))
        area = f"M{px(0):.1f},{py(vals[0]):.1f} " + " ".join(f"L{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals))
        area += f" L{px(len(vals)-1):.1f},{pt+cH} L{px(0):.1f},{pt+cH} Z"
        # x-axis tick labels every 10 days
        ticks = ""
        for i in [0, 9, 19, 29]:
            if i < len(days):
                import calendar
                d = datetime.datetime.strptime(days[i], "%Y-%m-%d")
                lbl = d.strftime("%b %-d")
                ticks += f'<text x="{px(i):.1f}" y="{H-2}" fill="#bbb" font-size="9" text-anchor="middle" font-family="system-ui">{lbl}</text>'
        return (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:80px;display:block;overflow:visible">'
                f'<path d="{area}" fill="{color}" fill-opacity=".15"/>'
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
                f'{ticks}</svg>')

    def word_bars(rows):
        if not rows: return '<span style="color:#aaa;font-size:.8rem">No data yet.</span>'
        maxn = rows[0].n or 1
        out = []
        for i, r in enumerate(rows):
            pct = round(r.n / maxn * 100)
            out.append(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:7px">'
                f'<span style="color:#bbb;font-size:.65rem;width:14px;text-align:right">{i+1}</span>'
                f'<span style="flex:1;font-family:Georgia,serif;font-size:.84rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_h(r.word)}</span>'
                f'<div style="width:52px;height:4px;background:#eee;border-radius:2px"><div style="width:{pct}%;height:4px;background:#c47028;border-radius:2px"></div></div>'
                f'<span style="color:#aaa;font-size:.7rem;min-width:18px;text-align:right">{r.n}</span>'
                f'</div>'
            )
        return "".join(out)

    recent = (db.query(User).order_by(User.created_at.desc()).limit(20).all())

    def fmt_date(dt):
        if not dt: return "—"
        return dt.strftime("%b %-d, %Y %H:%M")

    def auth_bar(label, val, total, color):
        pct = round(val / total * 100) if total else 0
        return (f'<div style="margin-bottom:12px">'
                f'<div style="display:flex;justify-content:space-between;font-size:.78rem;color:#555;margin-bottom:4px">'
                f'<span>{label}</span><strong>{val}</strong></div>'
                f'<div style="height:7px;background:#eee;border-radius:4px">'
                f'<div style="width:{pct}%;height:7px;background:{color};border-radius:4px"></div></div></div>')

    # ── Build HTML ────────────────────────────────────────────────────────────
    def card(label, val, sub=""):
        return (f'<div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">'
                f'<div style="font-size:.68rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">{label}</div>'
                f'<div style="font-size:1.8rem;font-weight:700;color:#111;line-height:1">{val:,}</div>'
                f'{"<div style=font-size:.72rem;color:#999;margin-top:5px>" + sub + "</div>" if sub else ""}'
                f'</div>')

    def sec(title):
        return f'<div style="font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#999;margin:28px 0 12px">{title}</div>'

    health_chips = [
        ("API", True, False),
        ("Database", True, False),
        ("Anthropic key", bool(os.getenv("ANTHROPIC_API_KEY")), False),
        ("Google OAuth", bool(os.getenv("GOOGLE_CLIENT_ID")), not bool(os.getenv("GOOGLE_CLIENT_ID"))),
    ]

    # Disk
    stat = os.statvfs("/")
    disk_used_gb = round((stat.f_blocks - stat.f_bfree) * stat.f_frsize / 1e9, 1)
    disk_total_gb = round(stat.f_blocks * stat.f_frsize / 1e9, 1)
    disk_pct = round((stat.f_blocks - stat.f_bfree) / stat.f_blocks * 100, 1) if stat.f_blocks else 0
    health_chips.append((f"Disk {disk_used_gb}/{disk_total_gb} GB ({disk_pct}%)", disk_pct < 85, disk_pct > 70))

    uptime_s = int((now - _START_TIME).total_seconds())
    d, rem = divmod(uptime_s, 86400); h, rem = divmod(rem, 3600); m = rem // 60
    uptime_str = (f"{d}d {h}h" if d else f"{h}h {m}m" if h else f"{m}m")
    health_chips.append((f"Uptime {uptime_str}", True, False))

    def chip(label, ok, warn=False):
        dot = "#f59e0b" if warn else ("#22c55e" if ok else "#ef4444")
        return (f'<span style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;'
                f'background:#fff;border:1px solid #e5e5e5;border-radius:20px;font-size:.78rem;font-weight:500;margin:4px">'
                f'<span style="width:8px;height:8px;border-radius:50%;background:{dot};flex-shrink:0;display:inline-block"></span>'
                f'{label}</span>')

    def _h(s): return _html.escape(str(s or "—"))

    tr_rows = "".join(
        f'<tr style="border-bottom:1px solid #f0f0f0;cursor:pointer" onclick="location.href=\'/admin/user/{u.id}\'">'
        f'<td style="padding:9px 14px;color:#aaa">{u.id}</td>'
        f'<td style="padding:9px 14px"><a href="/admin/user/{u.id}" style="color:#c47028;font-weight:500;text-decoration:none">{_h(u.name or "—")}</a></td>'
        f'<td style="padding:9px 14px">{_h(u.email)}</td>'
        f'<td style="padding:9px 14px"><span style="padding:2px 8px;border-radius:20px;font-size:.65rem;font-weight:700;text-transform:uppercase;'
        f'background:{"#dbeafe;color:#1d4ed8" if u.google_id else "#dcfce7;color:#15803d"}">'
        f'{"oauth" if u.google_id else "password"}</span></td>'
        f'<td style="padding:9px 14px;color:#aaa">{fmt_date(u.created_at)}</td>'
        f'</tr>'
        for u in recent
    )

    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lexio Admin</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#f5f4f0;color:#1a1a1a;font-size:14px}}
a{{color:#c47028;text-decoration:none}}
</style>
</head><body>

<div style="display:flex;align-items:center;gap:10px;padding:14px 24px;background:#fff;border-bottom:1px solid #e5e5e5;position:sticky;top:0;z-index:10">
  <svg width="22" height="22" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="9" fill="#c47028"/><text x="18" y="25" font-family="Georgia,serif" font-size="20" font-weight="700" fill="white" text-anchor="middle">w</text></svg>
  <strong>Lexio</strong>
  <span style="font-size:.65rem;font-weight:700;padding:2px 7px;background:#fef3e2;color:#c47028;border-radius:20px;text-transform:uppercase;letter-spacing:.04em">Admin</span>
  <span style="margin-left:auto;font-size:.75rem;color:#aaa">Generated {now.strftime("%b %-d, %Y %H:%M")} UTC</span>
  <a href="/admin" style="margin-left:12px;padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555">↻ Refresh</a>
  <a href="/admin" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555">Sign out</a>
</div>

<div style="padding:24px;max-width:1280px;margin:0 auto">

  {sec("System health")}
  <div>{"".join(chip(label, ok, warn) for label, ok, warn in health_chips)}</div>

  {sec("Overview")}
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px">
    {card("Total users", total_users, f"+{users_week} this week · +{users_month} this month")}
    {card("Total searches", total_searches, f"+{searches_week} this week · +{searches_month} this month")}
    {card("Word bank entries", total_wb, f"+{wb_today} today")}
    {card("New users today", users_today, f"{users_week} this week")}
    {card("Searches today", searches_today, f"{searches_week} this week")}
    {card("WB entries today", wb_today, "")}
  </div>

  {sec("Trends — last 30 days")}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">Searches per day</div>
      {sparkline(search_map, "#c47028")}
    </div>
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">New users per day</div>
      {sparkline(user_map, "#3b82f6")}
    </div>
  </div>

  {sec("Top words &amp; auth")}
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px">
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">Top words — this month</div>
      {word_bars(top_month_rows)}
    </div>
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">Top words — all time</div>
      {word_bars(top_all_rows)}
    </div>
    <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">
      <div style="font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#999;margin-bottom:12px">Auth breakdown</div>
      {auth_bar("Google / Apple", oauth_users, total_users, "#3b82f6")}
      {auth_bar("Email / password", pwd_users, total_users, "#22c55e")}
    </div>
  </div>

  {sec("Recent sign-ups")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden;overflow-x:auto">
    <table style="width:100%;border-collapse:collapse">
      <thead><tr style="border-bottom:1px solid #eee">
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">#</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Name</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Email</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Auth</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Joined</th>
      </tr></thead>
      <tbody>{tr_rows}</tbody>
    </table>
  </div>

</div>
</body></html>"""

    return HTMLResponse(html)


# ── /admin/user/{user_id} ────────────────────────────────────────────────────
@app.get("/admin/user/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(user_id: int, request: Request, db: DBSession = Depends(get_db)):
    if not _verify_admin_cookie(request):
        return HTMLResponse('<meta http-equiv="refresh" content="0;url=/admin">', status_code=302)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return HTMLResponse("<h1>User not found</h1>", status_code=404)

    now        = datetime.datetime.utcnow()
    thirty_ago = (now - datetime.timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Per-user search stats ──────────────────────────────────────────────────
    total_searches = db.query(func.count(UserSearchLog.id)).filter(UserSearchLog.user_id == user_id).scalar() or 0

    daily_rows = (
        db.query(func.date(UserSearchLog.searched_at).label("day"), func.count(UserSearchLog.id).label("n"))
        .filter(UserSearchLog.user_id == user_id, UserSearchLog.searched_at >= thirty_ago)
        .group_by(func.date(UserSearchLog.searched_at))
        .all()
    )
    daily_map = {r.day: r.n for r in daily_rows}
    days = [(thirty_ago + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
    daily_counts = [daily_map.get(d, 0) for d in days]

    top_words = (
        db.query(UserSearchLog.word, func.count(UserSearchLog.id).label("n"))
        .filter(UserSearchLog.user_id == user_id)
        .group_by(UserSearchLog.word)
        .order_by(func.count(UserSearchLog.id).desc())
        .limit(15)
        .all()
    )

    wb_entries = (
        db.query(WordBankEntry)
        .filter(WordBankEntry.user_id == user_id)
        .order_by(WordBankEntry.saved_at.desc())
        .all()
    )

    def _h(s): return _html.escape(str(s or "—"))

    # ── Sparkline ─────────────────────────────────────────────────────────────
    maxv = max(daily_counts) if daily_counts else 1
    maxv = maxv or 1
    W, H, pl, pr, pt, pb = 800, 120, 40, 12, 8, 24
    cW, cH = W - pl - pr, H - pt - pb
    n = len(daily_counts)
    def px(i): return pl + (i / (n - 1)) * cW if n > 1 else pl
    def py(v): return pt + cH - (v / maxv) * cH
    pts  = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(daily_counts))
    area = f"M{px(0):.1f},{py(daily_counts[0]):.1f} " + " ".join(f"L{px(i):.1f},{py(v):.1f}" for i, v in enumerate(daily_counts))
    area += f" L{px(n-1):.1f},{pt+cH} L{px(0):.1f},{pt+cH} Z"
    tick_html = ""
    for i in [0, 9, 19, 29]:
        if i < len(days):
            d = datetime.datetime.strptime(days[i], "%Y-%m-%d")
            lbl = d.strftime("%b %-d")
            tick_html += f'<text x="{px(i):.1f}" y="{H-2}" fill="#bbb" font-size="10" text-anchor="middle" font-family="system-ui">{lbl}</text>'
    # Y-axis
    for f in [0.5, 1.0]:
        y = py(maxv * f)
        tick_html += f'<line x1="{pl}" y1="{y:.1f}" x2="{pl+cW}" y2="{y:.1f}" stroke="#eee" stroke-width="1"/>'
        tick_html += f'<text x="{pl-4}" y="{y+4:.1f}" fill="#bbb" font-size="9" text-anchor="end" font-family="system-ui">{round(maxv*f)}</text>'
    sparkline_svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:100px;display:block;overflow:visible">'
                     f'<path d="{area}" fill="#c47028" fill-opacity=".12"/>'
                     f'<polyline points="{pts}" fill="none" stroke="#c47028" stroke-width="2" stroke-linejoin="round"/>'
                     f'{tick_html}</svg>')

    # ── Daily table ────────────────────────────────────────────────────────────
    daily_table_rows = ""
    for i in range(29, -1, -1):
        d   = days[i]
        cnt = daily_counts[i]
        if cnt == 0 and i < 25:
            continue  # skip old zero days to keep table concise
        dt  = datetime.datetime.strptime(d, "%Y-%m-%d")
        lbl = dt.strftime("%b %-d, %Y")
        bar = f'<div style="height:6px;background:#eee;border-radius:3px;width:120px"><div style="width:{round(cnt/maxv*100)}%;height:6px;background:#c47028;border-radius:3px"></div></div>'
        daily_table_rows += (
            f'<tr style="border-bottom:1px solid #f0f0f0">'
            f'<td style="padding:8px 14px;color:#555">{lbl}</td>'
            f'<td style="padding:8px 14px;font-weight:600">{cnt}</td>'
            f'<td style="padding:8px 14px">{bar}</td>'
            f'</tr>'
        )

    # ── Top words ──────────────────────────────────────────────────────────────
    top_words_html = ""
    if top_words:
        mx = top_words[0].n or 1
        for i, r in enumerate(top_words):
            pct = round(r.n / mx * 100)
            top_words_html += (
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
                f'<span style="color:#bbb;font-size:.65rem;width:14px;text-align:right">{i+1}</span>'
                f'<span style="flex:1;font-family:Georgia,serif;font-size:.85rem">{_h(r.word)}</span>'
                f'<div style="width:60px;height:4px;background:#eee;border-radius:2px"><div style="width:{pct}%;height:4px;background:#c47028;border-radius:2px"></div></div>'
                f'<span style="color:#aaa;font-size:.7rem;min-width:18px;text-align:right">{r.n}</span>'
                f'</div>'
            )
    else:
        top_words_html = '<span style="color:#aaa;font-size:.82rem">No searches recorded yet.</span>'

    # ── Word bank ──────────────────────────────────────────────────────────────
    wb_html = ""
    if wb_entries:
        for e in wb_entries:
            d = json.loads(e.data)
            saved = e.saved_at.strftime("%b %-d, %Y") if e.saved_at else "—"
            wb_html += (
                f'<tr style="border-bottom:1px solid #f0f0f0">'
                f'<td style="padding:8px 14px;font-family:Georgia,serif;font-weight:500">{_h(e.word)}</td>'
                f'<td style="padding:8px 14px;color:#555;font-size:.8rem">{_h(d.get("pos","—"))}</td>'
                f'<td style="padding:8px 14px;color:#555;font-size:.8rem;max-width:340px">{_h(d.get("definition","—"))}</td>'
                f'<td style="padding:8px 14px;color:#aaa;font-size:.78rem">{saved}</td>'
                f'</tr>'
            )
    else:
        wb_html = '<tr><td colspan="4" style="padding:12px 14px;color:#aaa">No words collected yet.</td></tr>'

    auth_label = "Google / Apple OAuth" if user.google_id else "Email / password"
    joined = user.created_at.strftime("%b %-d, %Y at %H:%M UTC") if user.created_at else "—"
    pro_label = "⭐ Pro" if user.is_pro else "Free tier"
    pro_val   = 1 if user.is_pro else 0
    pro_badge_style = "background:#fef3e2;color:#c47028;border-color:#f5c87a" if user.is_pro else "background:#f5f5f5;color:#666;border-color:#ddd"

    def sec(title):
        return f'<div style="font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#999;margin:28px 0 12px">{title}</div>'

    def card(label, val, sub=""):
        return (f'<div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:18px">'
                f'<div style="font-size:.68rem;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">{label}</div>'
                f'<div style="font-size:1.8rem;font-weight:700;color:#111;line-height:1">{val}</div>'
                f'{"<div style=font-size:.72rem;color:#999;margin-top:5px>" + sub + "</div>" if sub else ""}'
                f'</div>')

    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_h(user.name or user.email)} — Lexio Admin</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:system-ui,sans-serif;background:#f5f4f0;color:#1a1a1a;font-size:14px}}</style>
</head><body>

<div style="display:flex;align-items:center;gap:10px;padding:14px 24px;background:#fff;border-bottom:1px solid #e5e5e5;position:sticky;top:0;z-index:10">
  <svg width="22" height="22" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="9" fill="#c47028"/><text x="18" y="25" font-family="Georgia,serif" font-size="20" font-weight="700" fill="white" text-anchor="middle">w</text></svg>
  <strong>Lexio</strong>
  <span style="font-size:.65rem;font-weight:700;padding:2px 7px;background:#fef3e2;color:#c47028;border-radius:20px;text-transform:uppercase;letter-spacing:.04em">Admin</span>
  <span style="color:#ddd;margin:0 4px">/</span>
  <span style="font-size:.9rem;color:#555">User #{user.id}</span>
  <div style="margin-left:auto;display:flex;gap:10px">
    <a href="/admin" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555;text-decoration:none">← Dashboard</a>
    <a href="/admin/user/{user_id}" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555;text-decoration:none">↻ Refresh</a>
  </div>
</div>

<div style="padding:24px;max-width:1100px;margin:0 auto">

  <!-- User info -->
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:20px;display:flex;align-items:center;gap:18px;margin-bottom:4px">
    <div style="width:52px;height:52px;border-radius:50%;background:#c47028;color:#fff;font-size:1.3rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0">
      {_h((user.name or user.email)[0].upper())}
    </div>
    <div>
      <div style="font-size:1.05rem;font-weight:700">{_h(user.name or "—")}</div>
      <div style="color:#777;font-size:.85rem;margin-top:2px">{_h(user.email)}</div>
      <div style="color:#aaa;font-size:.75rem;margin-top:4px">{auth_label} · Joined {joined}</div>
      <div style="margin-top:8px">
        <button onclick="togglePro()" id="pro-btn" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;cursor:pointer;{pro_badge_style}">{pro_label}</button>
      </div>
    </div>
  </div>
  <script>
  async function togglePro() {{
    const newVal = {pro_val} ? 0 : 1;
    await fetch('/admin/user/{user_id}/set-pro', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{is_pro: newVal}})
    }});
    location.reload();
  }}
  </script>

  {sec("Usage overview")}
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px">
    {card("Total lookups", f"{total_searches:,}")}
    {card("Words collected", f"{len(wb_entries):,}")}
    {card("Auth method", "OAuth" if user.google_id else "Password")}
  </div>

  {sec("Lookups per day — last 30 days")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:20px">
    {sparkline_svg}
  </div>

  {sec("Day-by-day breakdown")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden">
    <table style="width:100%;border-collapse:collapse">
      <thead><tr style="border-bottom:1px solid #eee">
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Date</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Lookups</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa"></th>
      </tr></thead>
      <tbody>{daily_table_rows or '<tr><td colspan="3" style="padding:12px 14px;color:#aaa">No activity yet.</td></tr>'}</tbody>
    </table>
  </div>

  {sec("Most looked-up words")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:20px">
    {top_words_html}
  </div>

  {sec(f"Word bank ({len(wb_entries)} words)")}
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden">
    <table style="width:100%;border-collapse:collapse">
      <thead><tr style="border-bottom:1px solid #eee">
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Word</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">POS</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Definition</th>
        <th style="text-align:left;padding:10px 14px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#aaa">Saved</th>
      </tr></thead>
      <tbody>{wb_html}</tbody>
    </table>
  </div>

</div>
</body></html>"""

    return HTMLResponse(html)


# ── /api/admin/user/{user_id}/set-pro (API key auth) ─────────────────────────

@app.post("/api/admin/user/{user_id}/set-pro")
async def admin_set_pro(
    user_id: int,
    body: dict,
    db: DBSession = Depends(get_db),
    _: None = Depends(_check_admin),
):
    """Toggle is_pro for a user. Body: {"is_pro": 0|1}"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    is_pro = int(bool(body.get("is_pro", 0)))
    user.is_pro = is_pro
    db.commit()
    return {"user_id": user_id, "is_pro": is_pro}


@app.post("/admin/user/{user_id}/set-pro", response_class=JSONResponse)
async def admin_set_pro_ui(
    user_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
):
    if not _verify_admin_cookie(request):
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    is_pro = int(bool(body.get("is_pro", 0)))
    user.is_pro = is_pro
    db.commit()
    return {"user_id": user_id, "is_pro": is_pro}


# ── /ocr ─────────────────────────────────────────────────────────────────────

@app.post("/ocr")
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

    try:
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
            text = response.choices[0].message.content.strip()
        else:
            raise HTTPException(status_code=503, detail="No vision API key configured (GOOGLE_API_KEY or OPENAI_API_KEY required).")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("/ocr error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Image processing failed. Please try again.")

    if not text:
        raise HTTPException(status_code=422, detail="No text found in the image.")

    return {"text": text}


# ── /api/usage ────────────────────────────────────────────────────────────────

@app.get("/api/usage")
async def get_usage(request: Request, user: Optional[User] = Depends(optional_user),
                    db: DBSession = Depends(get_db)):
    """Return current-month usage for the caller (authenticated or anonymous)."""
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
        "lookup": {"used": row.lookups if row else 0, "limit": FREE_LOOKUP_LIMIT},
        "ocr":    {"used": row.ocr     if row else 0, "limit": FREE_OCR_LIMIT},
        "hourly": hourly_status,
    }


# ── Stripe ────────────────────────────────────────────────────────────────────
import stripe as _stripe
import httpx as _httpx

_stripe.api_key          = os.getenv("STRIPE_SECRET_KEY", "")
_STRIPE_WEBHOOK_SECRET   = os.getenv("STRIPE_WEBHOOK_SECRET", "")
_STRIPE_PRICE_ID         = os.getenv("STRIPE_PRICE_ID", "")   # single multi-currency price
_SITE_URL                = os.getenv("SITE_URL", "https://lexio.site")

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
    """Return (currency_code, symbol, amount) for the visitor's country."""
    if country in _GBP_COUNTRIES:
        return "GBP", "£", "2.99"
    if country in _EUR_COUNTRIES:
        return "EUR", "€", "2.99"
    return "USD", "$", "3.99"


@app.get("/stripe/price-info")
async def stripe_price_info(request: Request):
    """Return currency symbol & amount for the visitor's location (no auth needed)."""
    ip = request.client.host
    # Prefer X-Forwarded-For when behind a proxy
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    country = await _country_from_ip(ip)
    currency, symbol, amount = _price_for_country(country)
    return {"currency": currency, "symbol": symbol, "amount": amount, "country": country}


@app.post("/stripe/create-checkout")
async def stripe_create_checkout(
    request: Request,
    user: User = Depends(current_user),
):
    """Create a Stripe Checkout session and return its URL."""
    if not _stripe.api_key:
        raise HTTPException(status_code=503, detail="Payments not configured")

    ip = request.client.host
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    country = await _country_from_ip(ip)
    currency, _, _ = _price_for_country(country)

    if not _STRIPE_PRICE_ID:
        raise HTTPException(status_code=503, detail="Stripe price not configured")

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
    subscription_data = {
        "metadata": {"user_id": str(user.id)},
    }
    if is_trial_eligible:
        subscription_data["trial_period_days"] = TRIAL_DAYS
        # If the user removes their payment method mid-trial, cancel
        # automatically — never let a trial roll over without a card.
        subscription_data["trial_settings"] = {
            "end_behavior": {"missing_payment_method": "cancel"},
        }

    session = _stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": _STRIPE_PRICE_ID, "quantity": 1}],
        currency=currency.lower(),
        success_url=f"{_SITE_URL}/?stripe=success",
        cancel_url=f"{_SITE_URL}/?stripe=cancelled",
        metadata={"user_id": str(user.id), "trial": "1" if is_trial_eligible else "0"},
        subscription_data=subscription_data,
        payment_method_collection="always",   # require card even on trial
        allow_promotion_codes=True,
        **customer_kwargs,
    )
    return {"url": session.url}


@app.post("/stripe/customer-portal")
async def stripe_customer_portal(
    user: User = Depends(current_user),
):
    """Return a Stripe Billing Portal URL so the user can manage / cancel."""
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe subscription found")
    portal = _stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=_SITE_URL,
    )
    return {"url": portal.url}


@app.post("/stripe/webhook")
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
                # Persist trial_end so the UI can show "X days left" without
                # round-tripping to Stripe on every page load.
                if status == "trialing" and trial_end:
                    u.trial_expires_at = datetime.datetime.utcfromtimestamp(int(trial_end))
                elif status in ("active",) and u.trial_expires_at and u.trial_expires_at < datetime.datetime.utcnow():
                    # Trial → paid transition: clear stale trial_expires_at
                    u.trial_expires_at = None
                db.commit()
                logger.info(
                    "Stripe: %s status=%s → is_pro=%d trial_end=%s for user %d",
                    etype, status, u.is_pro, trial_end, u.id,
                )

    elif etype == "invoice.payment_failed":
        customer_id = obj.get("customer")
        if customer_id:
            u = db.query(User).filter(User.stripe_customer_id == customer_id).first()
            if u:
                logger.warning("Stripe: payment failed for user %d (%s)", u.id, customer_id)
            # Do not revoke immediately — Stripe will retry and send subscription.deleted if truly lapsed

    return {"received": True}


# ── /api/pro-status ───────────────────────────────────────────────────────────

@app.get("/api/pro-status")
async def pro_status(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    """Return Pro/trial status for the authenticated user."""
    u = db.query(User).filter(User.id == user.id).first()
    # A user is "on trial" if they have a future trial_expires_at — regardless
    # of is_pro, because Stripe-trial users have is_pro=1 set by the
    # subscription webhook.
    trial = bool(u and u.trial_expires_at and u.trial_expires_at > datetime.datetime.utcnow())
    paid  = bool(u and u.is_pro and not trial)
    days  = _trial_days_left(u) if u else 0
    return {"is_pro": paid or trial, "is_trial": trial, "trial_days_left": days}


# ── Named static page routes ─────────────────────────────────────────────────

@app.get("/pro", response_class=HTMLResponse, include_in_schema=False)
async def pro_page():
    with open("static/pro/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_page():
    with open("static/privacy.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ── Static frontend ───────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")
