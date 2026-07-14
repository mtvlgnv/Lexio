"""Hand-rolled SQLite column migrations, tracked in schema_version (Phase 2 extract)."""
import logging

from app.db import engine, Base

logger = logging.getLogger("lexio")


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
    # Email verification: existing accounts are grandfathered to verified=1
    # so we don't lock anyone out of their existing Pro subscription.
    (13, "add email verification columns", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("email_verified",          "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1"),
            ("email_verify_code",       "ALTER TABLE users ADD COLUMN email_verify_code TEXT"),
            ("email_verify_expires_at", "ALTER TABLE users ADD COLUMN email_verify_expires_at TIMESTAMP"),
        ] if col not in _cols(conn, "users")
    ]),
    # Active sessions: JSON list of recent jtis, capped at 5 per user
    # (Gap 1 — concurrent device limit). Legacy tokens (no jti) keep working
    # until natural expiration; new tokens are session-bound.
    (14, "add active_jtis + last_login columns", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("active_jtis",   "ALTER TABLE users ADD COLUMN active_jtis TEXT NOT NULL DEFAULT '[]'"),
            ("last_login_at", "ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP"),
            ("last_login_ua", "ALTER TABLE users ADD COLUMN last_login_ua TEXT"),
        ] if col not in _cols(conn, "users")
    ]),
    # Subscription metadata (annual vs monthly), founder badge, family plan.
    (15, "add subscription metadata + family columns", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("subscription_interval", "ALTER TABLE users ADD COLUMN subscription_interval TEXT"),
            ("subscription_status",   "ALTER TABLE users ADD COLUMN subscription_status TEXT"),
            ("is_founder",            "ALTER TABLE users ADD COLUMN is_founder INTEGER NOT NULL DEFAULT 0"),
            ("family_owner_id",       "ALTER TABLE users ADD COLUMN family_owner_id INTEGER REFERENCES users(id)"),
        ] if col not in _cols(conn, "users")
    ]),
    (16, "create family_invitations table", lambda conn, _: conn.execute(_sa_text("""
        CREATE TABLE IF NOT EXISTS family_invitations (
            id           INTEGER PRIMARY KEY,
            owner_id     INTEGER NOT NULL REFERENCES users(id),
            email        TEXT NOT NULL,
            token        TEXT UNIQUE NOT NULL,
            expires_at   TIMESTAMP NOT NULL,
            accepted_at  TIMESTAMP,
            accepted_by  INTEGER REFERENCES users(id),
            created_at   TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
        )
    """))),
    # Weekly re-engagement digest (retention): opt-out flag + throttle timestamp.
    (17, "add digest opt-out + last_digest_at", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("digest_opt_out", "ALTER TABLE users ADD COLUMN digest_opt_out INTEGER NOT NULL DEFAULT 0"),
            ("last_digest_at", "ALTER TABLE users ADD COLUMN last_digest_at TIMESTAMP"),
        ] if col not in _cols(conn, "users")
    ]),
    # Reader profile (ROADMAP P1-5 Phase 1): one JSON blob
    # {about, english_level, native_lang} — nullable, feeds /define prompts
    # for signed-in users so definitions land in the reader's world.
    (18, "add profile_json", lambda conn, _: (
        conn.execute(_sa_text("ALTER TABLE users ADD COLUMN profile_json TEXT"))
        if "profile_json" not in _cols(conn, "users") else None
    )),
    # Apple In-App Purchase (Mac App Store build): who bought via Apple and
    # until when. Pro state itself stays in is_pro, same as Stripe — these
    # let /apple/verify-receipt re-validate and expire Apple-sourced Pro
    # without touching Stripe subscribers.
    (19, "add Apple IAP columns", lambda conn, _: [
        conn.execute(_sa_text(ddl))
        for col, ddl in [
            ("apple_original_transaction_id",
             "ALTER TABLE users ADD COLUMN apple_original_transaction_id TEXT"),
            ("apple_expires_at",
             "ALTER TABLE users ADD COLUMN apple_expires_at TIMESTAMP"),
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
