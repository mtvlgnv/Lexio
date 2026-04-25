import asyncio
import os
import json
import secrets
import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends, Header, BackgroundTasks
from sqlalchemy import func
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, AnyHttpUrl, EmailStr
import anthropic
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
    id         = Column(Integer, primary_key=True, index=True)
    email      = Column(String, unique=True, nullable=False, index=True)
    name       = Column(String, nullable=True)
    pwd_hash   = Column(String, nullable=True)   # nullable for OAuth-only users
    google_id  = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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

Base.metadata.create_all(engine)

# ── SQLite migrations (add columns that may not exist yet) ────────────────────
def _run_migrations():
    with engine.connect() as conn:
        # Add google_id column if missing
        cols = [row[1] for row in conn.execute(__import__('sqlalchemy').text("PRAGMA table_info(users)"))]
        if "google_id" not in cols:
            conn.execute(__import__('sqlalchemy').text("ALTER TABLE users ADD COLUMN google_id TEXT"))
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

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ── Request / response models ─────────────────────────────────────────────────

class DefineRequest(BaseModel):
    word:    str = Field(..., min_length=1, max_length=60)
    context: str = Field(..., min_length=1, max_length=8_000)
    lang:    str = Field(default="auto", max_length=40)

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


# ── /define ──────────────────────────────────────────────────────────────────

LANG_NAMES = {
    'en':'English','es':'Spanish','fr':'French','de':'German','it':'Italian',
    'pt':'Portuguese','ru':'Russian','zh':'Chinese','ja':'Japanese','ko':'Korean',
    'ar':'Arabic','hi':'Hindi','nl':'Dutch','pl':'Polish','tr':'Turkish','sv':'Swedish',
}

@app.post("/define")
@limiter.limit("20/minute")
async def define_word(request: Request, req: DefineRequest, bg: BackgroundTasks):
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

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text  = "\n".join(l for l in lines if not l.startswith("```")).strip()

        result = json.loads(text)
        for key in required_keys:
            if key not in result:
                raise ValueError(f"Missing key: {key}")

        # Log the search anonymously after we know the response was good
        bg.add_task(_log_search, req.word)
        return result

    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to parse model response: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {exc}")


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


# ── Static frontend ───────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")
