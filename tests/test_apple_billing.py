"""Apple IAP receipt validation (/apple/verify-receipt) — MAS build backend.

Apple's verifyReceipt is mocked at the router boundary (_verify_with_apple);
these cover the grant/expire/reject paths and the not-configured guard.
"""
import datetime
import uuid

from fastapi.testclient import TestClient

import main
from app.routers import apple_billing

client = TestClient(main.app)

RECEIPT = {"receipt": "x" * 40}  # shape-valid base64ish blob


def _register():
    email = f"apple{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password-123"},
        headers={"X-Real-IP": "10.9.8.7"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _apple_response(expires_in_days, product="site.lexio.pro.monthly", status=0):
    ms = int((datetime.datetime.utcnow()
              + datetime.timedelta(days=expires_in_days)).timestamp() * 1000)
    return {
        "status": status,
        "latest_receipt_info": [{
            "product_id": product,
            "expires_date_ms": str(ms),
            "original_transaction_id": "1000000000000001",
        }],
    }


def test_verify_receipt_requires_auth():
    r = client.post("/apple/verify-receipt", json=RECEIPT)
    assert r.status_code in (401, 403)


def test_verify_receipt_unconfigured_returns_503(monkeypatch):
    monkeypatch.setattr(apple_billing, "_APPLE_SHARED_SECRET", "")
    r = client.post("/apple/verify-receipt", json=RECEIPT, headers=_register())
    assert r.status_code == 503


def test_active_subscription_grants_pro(monkeypatch):
    monkeypatch.setattr(apple_billing, "_APPLE_SHARED_SECRET", "test-secret")

    async def fake_verify(_):
        return _apple_response(expires_in_days=30)
    monkeypatch.setattr(apple_billing, "_verify_with_apple", fake_verify)

    headers = _register()
    r = client.post("/apple/verify-receipt", json=RECEIPT, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_pro"] is True
    assert body["source"] == "apple"
    assert body["expires_at"]

    # Pro is visible through the normal status endpoint too.
    r2 = client.get("/api/pro-status", headers=headers)
    assert r2.status_code == 200 and r2.json()["is_pro"] is True


def test_expired_subscription_revokes_apple_sourced_pro(monkeypatch):
    monkeypatch.setattr(apple_billing, "_APPLE_SHARED_SECRET", "test-secret")
    headers = _register()

    async def active(_):
        return _apple_response(expires_in_days=30)
    monkeypatch.setattr(apple_billing, "_verify_with_apple", active)
    assert client.post("/apple/verify-receipt", json=RECEIPT, headers=headers).json()["is_pro"] is True

    async def expired(_):
        return _apple_response(expires_in_days=-1, status=21006)
    monkeypatch.setattr(apple_billing, "_verify_with_apple", expired)
    r = client.post("/apple/verify-receipt", json=RECEIPT, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["is_pro"] is False


def test_rejected_receipt_400(monkeypatch):
    monkeypatch.setattr(apple_billing, "_APPLE_SHARED_SECRET", "test-secret")

    async def bad(_):
        return {"status": 21003}   # "receipt could not be authenticated"
    monkeypatch.setattr(apple_billing, "_verify_with_apple", bad)
    r = client.post("/apple/verify-receipt", json=RECEIPT, headers=_register())
    assert r.status_code == 400
