"""Lexio application entrypoint.

After the Phase 2 refactor this file is a thin assembler: it loads config,
runs DB setup + migrations, creates the FastAPI app, wires shared middleware
and the slowapi limiter, and includes the routers that live under app/routers/.
All request handlers now live in those router modules.

A few names are re-exported here (noqa: F401) purely because the test suite
reads them off `main` (main.User, main.SessionLocal, main.engine, the limit
constants, and main._get_client_ip).
"""
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lexio")

# ── Database + schema ────────────────────────────────────────────────────────
# Importing app.models creates the tables (Base.metadata.create_all); the
# hand-rolled column migrations then bring older databases up to date.
from app.db import engine, SessionLocal  # noqa: F401  (re-exported for tests)
from app.models import (  # noqa: F401  (import side effect: create_all; re-exported for tests)
    User, WordBankEntry, SearchLog, UserSearchLog,
    AnonUsage, PasswordResetToken, FamilyInvitation,
)
from app.migrations import _run_migrations

_run_migrations()

# Re-exported for the test suite (tests read these off `main`).
from app.config import (  # noqa: F401
    ANON_LOOKUP_LIMIT, FREE_LOOKUP_LIMIT, HOURLY_LIMIT_FREE,
)
from app.limits import _get_client_ip  # noqa: F401

# ── App + middleware ─────────────────────────────────────────────────────────
from app.ratelimit import limiter

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

# ── Routers ──────────────────────────────────────────────────────────────────
from app.routers.define import router as define_router
from app.routers.tools import router as tools_router
from app.routers.auth import router as auth_router
from app.routers.wordbank import router as wordbank_router
from app.routers.account import router as account_router
from app.routers.family import router as family_router
from app.routers.admin import router as admin_router
from app.routers.billing import router as billing_router
from app.routers.apple_billing import router as apple_billing_router
from app.routers.content import router as content_router
from app.routers.feedback import router as feedback_router

app.include_router(define_router)
app.include_router(tools_router)
app.include_router(auth_router)
app.include_router(wordbank_router)
app.include_router(account_router)
app.include_router(family_router)
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(apple_billing_router)
app.include_router(content_router)
app.include_router(feedback_router)

# ── Static frontend (mounted last so routes take precedence) ─────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")
