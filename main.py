import asyncio
import os
import json
import secrets
import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends, Header
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
    pwd_hash   = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class WordBankEntry(Base):
    __tablename__ = "wordbank"
    id       = Column(Integer, primary_key=True)
    user_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    word     = Column(String, nullable=False)
    data     = Column(Text, nullable=False)   # full JSON blob
    saved_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(engine)


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


# ── /define ──────────────────────────────────────────────────────────────────

@app.post("/define")
@limiter.limit("20/minute")
async def define_word(request: Request, req: DefineRequest):
    lang_note = (
        f"Respond in {req.lang}."
        if req.lang and req.lang.lower() not in ("auto", "detect", "")
        else "Respond in the same language as the input text."
    )
    prompt = (
        f'The word "{req.word}" appears in this text: "{req.context}"\n'
        f"{lang_note} Respond ONLY in JSON with no markdown:\n"
        '{"pos": "noun/verb/etc (in English)", '
        '"ipa": "IPA transcription e.g. /ɪˈfɛm.ər.əl/ — or null if uncertain", '
        '"contextual": "definition as used in this passage, 1-2 sentences", '
        '"why": "why this word rather than a simpler synonym, 1 sentence", '
        '"simpler": "the simplest common one-word synonym, or null if none", '
        '"etymology": "brief word origin, e.g. \'from Latin ephemeron\' — or null if uncertain", '
        '"register": "exactly one of: formal, literary, technical, colloquial, neutral, archaic"}'
    )

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text  = "\n".join(l for l in lines if not l.startswith("```")).strip()

        result = json.loads(text)
        for key in ("pos", "contextual", "why"):
            if key not in result:
                raise ValueError(f"Missing key: {key}")
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
    if not user or not verify_password(body.password, user.pwd_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"token": create_token(user.id), "user": {"id": user.id, "email": user.email, "name": user.name}}


# ── /auth/me ──────────────────────────────────────────────────────────────────

@app.get("/auth/me")
async def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}


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
