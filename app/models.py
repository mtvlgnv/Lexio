"""SQLAlchemy ORM models.

Extracted verbatim from main.py (Phase 2). Importing this module also runs
Base.metadata.create_all(engine), preserving the original import-time table
creation. The hand-rolled column migrations still live in main.py and run
immediately after this import, so ordering is unchanged.
"""
import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey

from app.db import Base, engine


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
    # Email verification (Gap 4) — OAuth users auto-verified, password
    # registrations require a 6-digit code if SMTP is configured.
    email_verified           = Column(Integer, default=1, nullable=False)   # 1=verified
    email_verify_code        = Column(String, nullable=True)
    email_verify_expires_at  = Column(DateTime, nullable=True)
    # Active JWT session tracking (Gap 1) — JSON list of dicts:
    #   [{"jti": "...", "iat": "ISO timestamp", "ua": "User-Agent label"}, …]
    # Capped at MAX_SESSIONS_PER_USER, oldest pruned on new login.
    active_jtis      = Column(Text, default="[]", nullable=False)
    last_login_at    = Column(DateTime, nullable=True)
    last_login_ua    = Column(String, nullable=True)
    # Stripe subscription metadata — populated by the webhook on
    # checkout.session.completed. Used for the annual-bonus UI and the
    # family-plan check (only the plan owner sees the Family panel).
    subscription_interval = Column(String, nullable=True)   # 'month' | 'year' | 'family' | None
    subscription_status   = Column(String, nullable=True)   # 'active' | 'trialing' | 'canceled' | None
    # Founder flag — manually set for early supporters. Drives a small
    # badge in the account modal and unlocks the founder-only export.
    is_founder            = Column(Integer, default=0, nullable=False)
    # Family-plan membership: if set, this user inherits Pro from the owner.
    family_owner_id       = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # Weekly re-engagement digest (retention). digest_opt_out=1 suppresses it;
    # last_digest_at throttles to at most one send per DIGEST_INTERVAL_DAYS.
    digest_opt_out   = Column(Integer, default=0, nullable=False)
    last_digest_at   = Column(DateTime, nullable=True)
    # Reader profile (ROADMAP P1-5 Phase 1) — JSON blob:
    # {about, english_level, native_lang}. Nullable; feeds /define prompts
    # for signed-in users so domain sense/complexity land in their world.
    profile_json     = Column(Text, nullable=True)
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

class DefinitionFeedback(Base):
    """B13: 👍/👎 on a definition — the prompt-quality dataset. Anonymous by
    design (no user ID, no IP, no context text), same privacy posture as
    SearchLog above."""
    __tablename__ = "definition_feedback"
    id         = Column(Integer, primary_key=True)
    word       = Column(String, nullable=False, index=True)
    model      = Column(String, nullable=False)   # 'fast' | 'balanced' | 'deep'
    verdict    = Column(String, nullable=False)   # 'up' | 'down'
    lang       = Column(String, nullable=False)
    mode       = Column(String, nullable=False)   # 'text' | 'image'
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

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

class FamilyInvitation(Base):
    """Pending family-plan invitations. Created by a Pro family-plan owner,
    consumed when the invitee signs up and accepts. Tokens expire in 14 days."""
    __tablename__ = "family_invitations"
    id           = Column(Integer, primary_key=True)
    owner_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email        = Column(String, nullable=False, index=True)
    token        = Column(String, unique=True, nullable=False, index=True)
    expires_at   = Column(DateTime, nullable=False)
    accepted_at  = Column(DateTime, nullable=True)
    accepted_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(engine)
