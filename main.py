import asyncio
import os
import json
import secrets
import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends, Header, BackgroundTasks, File, UploadFile
from sqlalchemy import func
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
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
    preferred_model = Column(String, default="sonnet", nullable=False)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)

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

Base.metadata.create_all(engine)

# ── SQLite migrations (add columns that may not exist yet) ────────────────────
def _run_migrations():
    with engine.connect() as conn:
        # Add google_id column if missing
        cols = [row[1] for row in conn.execute(__import__('sqlalchemy').text("PRAGMA table_info(users)"))]
        if "google_id" not in cols:
            conn.execute(__import__('sqlalchemy').text("ALTER TABLE users ADD COLUMN google_id TEXT"))
            conn.commit()
        # Add preferred_model column if missing
        cols = [row[1] for row in conn.execute(__import__('sqlalchemy').text("PRAGMA table_info(users)"))]
        if "preferred_model" not in cols:
            conn.execute(__import__('sqlalchemy').text("ALTER TABLE users ADD COLUMN preferred_model TEXT DEFAULT 'haiku'"))
            conn.commit()

_run_migrations()

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
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
ALGORITHM  = "HS256"
TOKEN_TTL  = datetime.timedelta(days=90)


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.datetime.utcnow() + TOKEN_TTL,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> int:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(data["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def current_user(
    authorization: Optional[str] = Header(default=None),
    db: DBSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    uid   = decode_token(token)
    user  = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def optional_user(
    authorization: Optional[str] = Header(default=None),
    db: DBSession = Depends(get_db),
) -> Optional[User]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        token = authorization.split(" ", 1)[1]
        uid   = decode_token(token)
        return db.query(User).filter(User.id == uid).first()
    except HTTPException:
        return None


# ── Rate limiter ─────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)
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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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

class WBSyncRequest(BaseModel):
    entries: list[dict]   # list of word bank objects from the client


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
                      user: Optional[User] = Depends(optional_user)):
    lang_code    = (req.lang or 'auto').strip().lower()
    lang_name    = LANG_NAMES.get(lang_code)   # None if auto/unknown
    lang_note = (
        f"You MUST respond entirely in {lang_name}. Every field in the JSON must be written in {lang_name}, not English."
        if lang_name
        else "Respond in the same language as the input text."
    )

    word_count = len(req.word.strip().split())
    is_phrase   = word_count > 1

    if is_phrase:
        # Phrase / sentence: skip pos & ipa, focus on meaning and usage
        prompt = (
            f'The phrase or sentence "{req.word}" appears in this text: "{req.context}"\n'
            f"{lang_note} Respond ONLY in JSON with no markdown:\n"
            '{\"definition\": \"plain-English meaning of this phrase/sentence, 1-2 sentences\", '
            '\"contextual\": \"what it specifically means in this passage, 1-2 sentences\", '
            '\"why\": \"why the author chose this phrasing, 1 sentence\", '
            '\"register\": \"exactly one of: formal, literary, technical, colloquial, neutral, archaic\"}'
        )
        required_keys = ("definition", "contextual")
    else:
        # Single word: full analysis
        prompt = (
            f'The word "{req.word}" appears in this text: "{req.context}"\n'
            f"{lang_note} Respond ONLY in JSON with no markdown:\n"
            '{\"pos\": \"noun/verb/etc (in English)\", '
            '\"ipa\": \"IPA transcription e.g. /ɪˈfɛm.ər.əl/ — or null if uncertain\", '
            '\"definition\": \"general dictionary definition, 1 sentence\", '
            '\"contextual\": \"definition as used in this passage, 1-2 sentences\", '
            '\"why\": \"why this word rather than a simpler synonym, 1 sentence\", '
            '\"simpler\": \"the simplest common one-word synonym, or null if none\", '
            '\"etymology\": \"brief word origin, e.g. from Latin ephemeron — or null if uncertain\", '
            '\"register\": \"exactly one of: formal, literary, technical, colloquial, neutral, archaic\"}'
        )
        required_keys = ("pos", "contextual")

    # Determine which model to use
    model_choice = (req.model or "haiku").lower().strip()

    # Map user-friendly names to internal names
    model_map = {
        "haiku": "haiku",
        "gemini": "gemini",
        "gpt-4-mini": "gpt-4-mini",
        "gpt-4o-mini": "gpt-4-mini",  # alias
        "sonnet": "sonnet",
    }
    actual_model = model_map.get(model_choice, "haiku")  # default to haiku

    try:
        # Call the appropriate API
        if actual_model == "gemini":
            text = _call_google(prompt)
        elif actual_model in ("gpt-4-mini",):
            text = _call_openai(prompt)
        elif actual_model == "sonnet":
            text = _call_anthropic(prompt, "claude-sonnet-4-5-20250929")
        else:  # haiku (default)
            text = _call_anthropic(prompt, "claude-haiku-4-5-20251001")

        # Clean up markdown code blocks if present
        if text.startswith("```"):
            lines = text.splitlines()
            text  = "\n".join(l for l in lines if not l.startswith("```")).strip()

        result = json.loads(text)
        for key in required_keys:
            if key not in result:
                raise ValueError(f"Missing key: {key}")

        # Save user's model preference if authenticated
        if user:
            db = SessionLocal()
            try:
                user_record = db.query(User).filter(User.id == user.id).first()
                if user_record and user_record.preferred_model != actual_model:
                    user_record.preferred_model = actual_model
                    db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()

        # Log anonymously (always) and per-user (when authenticated)
        bg.add_task(_log_search, req.word)
        if user:
            bg.add_task(_log_user_search, user.id, req.word)
        return result

    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to parse model response: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"API error: {exc}")


# ── /fetch-text ───────────────────────────────────────────────────────────────

@app.post("/fetch-text")
@limiter.limit("5/minute")
async def fetch_article(request: Request, payload: FetchRequest):
    try:
        import trafilatura
        url = str(payload.url)

        def _extract() -> str | None:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            return trafilatura.extract(
                downloaded,
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
        raise HTTPException(status_code=422, detail=str(exc))


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
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id), "user": {"id": user.id, "email": user.email, "name": user.name}}


# ── /auth/login ───────────────────────────────────────────────────────────────

@app.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: DBSession = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not user.pwd_hash or not verify_password(body.password, user.pwd_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"token": create_token(user.id), "user": {"id": user.id, "email": user.email, "name": user.name}}


# ── /auth/me ──────────────────────────────────────────────────────────────────

@app.get("/auth/me")
async def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}


# ── /api/models ───────────────────────────────────────────────────────────────

@app.get("/api/models")
async def get_models():
    """Return available models and their status."""
    return {
        "models": [
            {
                "id": "haiku",
                "name": "Claude Haiku",
                "provider": "Anthropic",
                "available": True,  # Always available
                "description": "Fast and compact model"
            },
            {
                "id": "gpt-4-mini",
                "name": "GPT-4o Mini",
                "provider": "OpenAI",
                "available": bool(os.getenv("OPENAI_API_KEY")),
                "description": "Efficient and capable model"
            },
            {
                "id": "gemini",
                "name": "Gemini 2.5 Flash",
                "provider": "Google",
                "available": bool(os.getenv("GOOGLE_API_KEY")),
                "description": "Fast multimodal model"
            },
            {
                "id": "sonnet",
                "name": "Claude Sonnet 3.5",
                "provider": "Anthropic",
                "available": True,
                "description": "Advanced reasoning model"
            }
        ]
    }


@app.get("/api/user-model")
async def get_user_model(user: User = Depends(optional_user)):
    """Get the user's preferred model."""
    if not user:
        return {"model": "haiku"}
    db = SessionLocal()
    try:
        user_record = db.query(User).filter(User.id == user.id).first()
        if user_record:
            return {"model": user_record.preferred_model or "haiku"}
    finally:
        db.close()
    return {"model": "haiku"}


class ModelUpdateRequest(BaseModel):
    model: str = Field(..., max_length=40)


@app.post("/api/user-model")
async def update_user_model(req: ModelUpdateRequest, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    """Update the user's preferred model."""
    valid_models = {"haiku", "gpt-4-mini", "gemini", "sonnet"}
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
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "apple_services_id": os.getenv("APPLE_SERVICES_ID", ""),
    }


# ── /auth/google ──────────────────────────────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    credential: str

@app.post("/auth/google")
@limiter.limit("10/minute")
async def google_auth(request: Request, body: GoogleAuthRequest, db: DBSession = Depends(get_db)):
    """Verify Google ID token and sign in / register the user."""
    import asyncio, urllib.request as _ur, json as _json

    token = body.credential.strip()
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")

    # Verify token via Google's tokeninfo endpoint (no extra libraries needed)
    def _fetch_tokeninfo():
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
        try:
            with _ur.urlopen(url, timeout=6) as r:
                return _json.loads(r.read()), r.status
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Google token verification failed: {exc}")

    info, status = await asyncio.to_thread(_fetch_tokeninfo)

    if status != 200 or info.get("error"):
        raise HTTPException(status_code=401, detail="Invalid Google token.")

    # Validate audience (aud must match our client id)
    if google_client_id and info.get("aud") != google_client_id:
        raise HTTPException(status_code=401, detail="Token audience mismatch.")

    email = info.get("email")
    if not email or info.get("email_verified") != "true":
        raise HTTPException(status_code=401, detail="Google account email is not verified.")

    google_sub = info.get("sub")  # stable unique Google user ID
    name       = info.get("name") or email.split("@")[0]

    # Find existing user by email or google_id
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, name=name, google_id=google_sub, pwd_hash=None)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.google_id:
            user.google_id = google_sub
            db.commit()

    return {"token": create_token(user.id), "user": {"id": user.id, "email": user.email, "name": user.name}}


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
        raise HTTPException(status_code=502, detail=f"Could not fetch Apple public keys: {exc}")

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
        raise HTTPException(status_code=401, detail=f"Apple token invalid: {exc}")

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
        user = User(email=display_email, name=name, google_id=f"apple:{apple_sub}", pwd_hash=None)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.google_id:
            user.google_id = f"apple:{apple_sub}"
            db.commit()

    return {"token": create_token(user.id), "user": {"id": user.id, "email": user.email, "name": user.name}}


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
        word = (entry.get("word") or "").strip()
        if not word:
            continue
        key = word.lower()
        if key in existing:
            existing[key].data = json.dumps(entry)
        else:
            new_entry = WordBankEntry(
                user_id  = user.id,
                word     = word,
                data     = json.dumps(entry),
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


# ── /admin  (server-side rendered, no JS required) ───────────────────────────
from fastapi.responses import HTMLResponse

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
async def admin_page(key: str = "", db: DBSession = Depends(get_db)):
    admin_key = os.getenv("ADMIN_KEY", "")

    login_form = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
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
  <form method="get" action="/admin">
    <input name="key" type="password" placeholder="Admin key" autofocus>
    <button type="submit">Access dashboard</button>
  </form>
  {error}
</div></body></html>"""

    if not key or not admin_key or key != admin_key:
        error = '<p class="err">Wrong key.</p>' if key else ''
        return HTMLResponse(login_form.replace("{error}", error))

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
                f'<span style="flex:1;font-family:Georgia,serif;font-size:.84rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{r.word}</span>'
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

    tr_rows = "".join(
        f'<tr style="border-bottom:1px solid #f0f0f0;cursor:pointer" onclick="location.href=\'/admin/user/{u.id}?key={key}\'">'
        f'<td style="padding:9px 14px;color:#aaa">{u.id}</td>'
        f'<td style="padding:9px 14px"><a href="/admin/user/{u.id}?key={key}" style="color:#c47028;font-weight:500;text-decoration:none">{u.name or "—"}</a></td>'
        f'<td style="padding:9px 14px">{u.email}</td>'
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
  <a href="/admin?key={key}" style="margin-left:12px;padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555">↻ Refresh</a>
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
async def admin_user_detail(user_id: int, key: str = "", db: DBSession = Depends(get_db)):
    admin_key = os.getenv("ADMIN_KEY", "")
    if not key or not admin_key or key != admin_key:
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
                f'<span style="flex:1;font-family:Georgia,serif;font-size:.85rem">{r.word}</span>'
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
                f'<td style="padding:8px 14px;font-family:Georgia,serif;font-weight:500">{e.word}</td>'
                f'<td style="padding:8px 14px;color:#555;font-size:.8rem">{d.get("pos","—")}</td>'
                f'<td style="padding:8px 14px;color:#555;font-size:.8rem;max-width:340px">{d.get("definition","—")}</td>'
                f'<td style="padding:8px 14px;color:#aaa;font-size:.78rem">{saved}</td>'
                f'</tr>'
            )
    else:
        wb_html = '<tr><td colspan="4" style="padding:12px 14px;color:#aaa">No words collected yet.</td></tr>'

    auth_label = "Google / Apple OAuth" if user.google_id else "Email / password"
    joined = user.created_at.strftime("%b %-d, %Y at %H:%M UTC") if user.created_at else "—"

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
<title>{user.name or user.email} — Lexio Admin</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:system-ui,sans-serif;background:#f5f4f0;color:#1a1a1a;font-size:14px}}</style>
</head><body>

<div style="display:flex;align-items:center;gap:10px;padding:14px 24px;background:#fff;border-bottom:1px solid #e5e5e5;position:sticky;top:0;z-index:10">
  <svg width="22" height="22" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="9" fill="#c47028"/><text x="18" y="25" font-family="Georgia,serif" font-size="20" font-weight="700" fill="white" text-anchor="middle">w</text></svg>
  <strong>Lexio</strong>
  <span style="font-size:.65rem;font-weight:700;padding:2px 7px;background:#fef3e2;color:#c47028;border-radius:20px;text-transform:uppercase;letter-spacing:.04em">Admin</span>
  <span style="color:#ddd;margin:0 4px">/</span>
  <span style="font-size:.9rem;color:#555">User #{user.id}</span>
  <div style="margin-left:auto;display:flex;gap:10px">
    <a href="/admin?key={key}" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555;text-decoration:none">← Dashboard</a>
    <a href="/admin/user/{user_id}?key={key}" style="padding:5px 14px;border:1px solid #ddd;border-radius:20px;font-size:.8rem;color:#555;text-decoration:none">↻ Refresh</a>
  </div>
</div>

<div style="padding:24px;max-width:1100px;margin:0 auto">

  <!-- User info -->
  <div style="background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:20px;display:flex;align-items:center;gap:18px;margin-bottom:4px">
    <div style="width:52px;height:52px;border-radius:50%;background:#c47028;color:#fff;font-size:1.3rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0">
      {(user.name or user.email)[0].upper()}
    </div>
    <div>
      <div style="font-size:1.05rem;font-weight:700">{user.name or "—"}</div>
      <div style="color:#777;font-size:.85rem;margin-top:2px">{user.email}</div>
      <div style="color:#aaa;font-size:.75rem;margin-top:4px">{auth_label} · Joined {joined}</div>
    </div>
  </div>

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


# ── /ocr ─────────────────────────────────────────────────────────────────────

@app.post("/ocr")
@limiter.limit("5/minute")
async def ocr_image(request: Request, file: UploadFile = File(...)):
    """Extract text from an uploaded image using Gemini or OpenAI vision."""
    # Validate MIME type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Only image files are accepted.")

    # Read and validate size (10 MB max)
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Image must be smaller than 10 MB.")

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
            text = response.text.strip()
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
        raise HTTPException(status_code=502, detail=f"Vision API error: {exc}")

    if not text:
        raise HTTPException(status_code=422, detail="No text found in the image.")

    return {"text": text}


# ── Static frontend ───────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")
