"""
Core API tests: the Pro gate, usage limits, IP-spoofing resistance, auth,
the admin gate, the Stripe webhook, and the SQLite WAL configuration.

All AI provider calls are mocked (autouse fixture below) — no test touches
a real provider. Each test uses its own X-Real-IP so per-IP state (slowapi
buckets, anonymous usage rows) can't bleed between tests.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text

import main
from main import app

client = TestClient(app)

VALID_AI_JSON = json.dumps({
    "pos": "noun",
    "ipa": "/tɛst/",
    "definition": "a general definition",
    "contextual": "the contextual meaning",
    "why": "because",
    "simpler": "test",
    "etymology": "from Latin",
    "register": "neutral",
})


@pytest.fixture(autouse=True)
def _mock_ai(monkeypatch):
    # /define lives in app.routers.define and calls ai._call_* by attribute,
    # so patch the provider wrappers on the app.ai module.
    monkeypatch.setattr("app.ai._call_openai", lambda prompt: VALID_AI_JSON)
    monkeypatch.setattr("app.ai._call_google", lambda prompt: VALID_AI_JSON)
    monkeypatch.setattr("app.ai._call_anthropic", lambda prompt, model="": VALID_AI_JSON)


def _ip():
    """A unique fake client IP per call, delivered via X-Real-IP."""
    return f"203.0.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"


def _define(word="ephemeral", model="fast", ip=None, extra_headers=None, token=None):
    headers = {"X-Real-IP": ip or _ip()}
    if extra_headers:
        headers.update(extra_headers)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        "/define",
        json={"word": word, "context": "An ephemeral moment passed.", "model": model},
        headers=headers,
    )


def _register(ip=None):
    email = f"u{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password-123"},
        headers={"X-Real-IP": ip or _ip()},
    )
    assert r.status_code == 201, r.text
    return email, r.json()["token"]


# ── Pro gate ──────────────────────────────────────────────────────────────────

def test_balanced_and_deep_require_pro_for_anonymous():
    for model in ("balanced", "deep", "gemini", "sonnet"):
        r = _define(model=model)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "pro_required"


def test_deep_requires_pro_for_free_signed_in_user():
    _, token = _register()
    r = _define(model="deep", token=token)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "pro_required"


def test_pro_user_can_use_deep():
    email, token = _register()
    with main.SessionLocal() as db:
        u = db.query(main.User).filter(main.User.email == email).first()
        u.is_pro = 1
        db.commit()
    r = _define(model="deep", token=token)
    assert r.status_code == 200, r.text
    assert r.json()["contextual"] == "the contextual meaning"


# ── /define happy path ────────────────────────────────────────────────────────

def test_define_fast_anonymous_success():
    r = _define()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pos"] == "noun"
    assert body["contextual"] == "the contextual meaning"
    assert body["_usage"]["limit"] == main.ANON_LOOKUP_LIMIT
    assert body["_usage"]["used"] == 1


# ── Anonymous quota + IP-spoofing resistance ─────────────────────────────────

def test_anon_limit_enforced_and_xff_spoof_does_not_reset_it():
    ip = _ip()
    for i in range(main.ANON_LOOKUP_LIMIT):
        r = _define(ip=ip)
        assert r.status_code == 200, f"lookup {i + 1}: {r.text}"

    # Quota exhausted
    r = _define(ip=ip)
    assert r.status_code == 402
    assert r.json()["detail"]["code"] == "limit_exceeded"

    # Regression for the X-Forwarded-For spoof: a forged XFF header must not
    # change the caller's identity (nginx's X-Real-IP wins).
    r = _define(ip=ip, extra_headers={"X-Forwarded-For": "198.51.100.7"})
    assert r.status_code == 402, "forged X-Forwarded-For bypassed the anon quota"


def test_client_ip_ignores_forged_xff_first_entry():
    # Simulates nginx ($proxy_add_x_forwarded_for appends the real address):
    # the helper must take the trusted side, never the client-supplied entry.
    from fastapi import Request

    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"198.51.100.7, 203.0.113.50")],
        "client": ("127.0.0.1", 1234),
    }
    assert main._get_client_ip(Request(scope)) == "203.0.113.50"

    scope["headers"].append((b"x-real-ip", b"203.0.113.99"))
    assert main._get_client_ip(Request(scope)) == "203.0.113.99"


# ── Signed-in free-tier monthly limit ────────────────────────────────────────

def test_free_user_monthly_lookup_limit():
    email, token = _register()
    with main.SessionLocal() as db:
        u = db.query(main.User).filter(main.User.email == email).first()
        u.monthly_lookups = main.FREE_LOOKUP_LIMIT
        u.lookup_month = __import__("datetime").datetime.utcnow().strftime("%Y-%m")
        db.commit()
    r = _define(token=token)
    assert r.status_code == 402
    assert r.json()["detail"]["kind"] == "lookup"


def test_free_user_hourly_credit_limit():
    email, token = _register()
    with main.SessionLocal() as db:
        u = db.query(main.User).filter(main.User.email == email).first()
        u.hourly_weight_used = main.HOURLY_LIMIT_FREE
        u.hourly_window_start = __import__("datetime").datetime.utcnow()
        db.commit()
    r = _define(token=token)
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "hourly_limit"
    assert "retry-after" in {k.lower() for k in r.headers}


# ── Auth ─────────────────────────────────────────────────────────────────────

def test_register_login_me_flow():
    email, _ = _register()
    r = client.post(
        "/auth/login",
        json={"email": email, "password": "password-123"},
        headers={"X-Real-IP": _ip()},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


def test_login_wrong_password_rejected():
    email, _ = _register()
    r = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password"},
        headers={"X-Real-IP": _ip()},
    )
    assert r.status_code == 401


def test_wordbank_requires_auth():
    assert client.get("/wordbank").status_code == 401
    r = client.post("/wordbank/sync", json={"entries": []})
    assert r.status_code == 401


# ── Admin gate ───────────────────────────────────────────────────────────────

def test_admin_endpoints_require_key():
    assert client.get("/api/admin/health").status_code == 403
    assert (
        client.get("/api/admin/health", headers={"X-Admin-Key": "wrong"}).status_code
        == 403
    )
    r = client.get("/api/admin/health", headers={"X-Admin-Key": "test-admin-key"})
    assert r.status_code == 200
    assert r.json()["db"] is True


# ── Stripe webhook ───────────────────────────────────────────────────────────

def test_stripe_webhook_rejects_bad_signature():
    r = client.post(
        "/stripe/webhook",
        content=b'{"type": "checkout.session.completed"}',
        headers={"stripe-signature": "t=1,v1=forged"},
    )
    assert r.status_code == 400


# ── SQLite configuration ─────────────────────────────────────────────────────

def test_sqlite_runs_in_wal_mode_with_busy_timeout():
    with main.engine.connect() as conn:
        assert conn.execute(sa_text("PRAGMA journal_mode")).scalar() == "wal"
        assert int(conn.execute(sa_text("PRAGMA busy_timeout")).scalar()) >= 5000
