"""Database engine, session factory, and SQLite tuning.

Extracted verbatim from main.py (Phase 2). Importing this module creates the
engine and registers the WAL pragma listener. The relative sqlite path means
the engine binds to ./lexio.db in the current working directory, exactly as
before (tests chdir to a scratch dir first).
"""
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import declarative_base, sessionmaker, Session as DBSession  # noqa: F401

DATABASE_URL = "sqlite:///./lexio.db"
engine = create_engine(
    DATABASE_URL,
    # `timeout` is sqlite3's busy wait (seconds) — without it, concurrent
    # writes from multiple uvicorn workers raise "database is locked".
    connect_args={"check_same_thread": False, "timeout": 10},
)


@sa_event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    # WAL lets readers proceed during writes — required for multi-worker
    # uvicorn. Persistent: once set, the db file stays in WAL mode.
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=10000")
    cur.close()


Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
