import json
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

VALID_AI_JSON = json.dumps({
    "pos": "noun",
    "ipa": "/sməʊk/",
    "definition": "Smoke definition",
    "contextual": "the contextual meaning",
    "why": "because",
    "simpler": "test",
    "etymology": "from old english",
    "register": "neutral",
})

@pytest.fixture(autouse=True)
def _mock_ai(monkeypatch):
    monkeypatch.setattr("app.ai._call_groq", lambda prompt, phrase=False: VALID_AI_JSON)
    monkeypatch.setattr("app.ai._call_google", lambda prompt: VALID_AI_JSON)
    monkeypatch.setattr("app.ai._call_anthropic", lambda prompt, model="": VALID_AI_JSON)

def test_lexio_works_correctly():
    """
    A high-level smoke test to verify that the Lexio application
    is assembled correctly, the DB migrations have run, the frontend
    is served, and the core routing is functional.
    """
    # 1. Verify the frontend loads (the StaticFiles mount works)
    response = client.get("/")
    assert response.status_code == 200, "Frontend index.html failed to load."
    assert "text/html" in response.headers["content-type"]

    # 2. Verify an unauthenticated request to a protected route behaves correctly
    response = client.get("/wordbank")
    assert response.status_code == 401, "Expected 401 Unauthorized for /wordbank without auth."

    # 3. Verify the core /define endpoint is reachable and returns an expected schema
    # Note: AI calls are automatically mocked by the autouse fixture in conftest.py
    response = client.post(
        "/define",
        json={
            "word": "smoke",
            "context": "Smoke test for the Lexio app.",
            "model": "fast"
        },
        headers={"X-Real-IP": "127.0.0.1"} # provide required IP header
    )
    assert response.status_code == 200, f"Expected 200 OK from /define, got: {response.text}"
    data = response.json()
    assert "pos" in data
    assert "definition" in data
    assert "contextual" in data

    # 4. Verify admin gate works
    response = client.get("/api/admin/health", headers={"X-Admin-Key": "test-admin-key"})
    assert response.status_code == 200, "Admin health endpoint failed."
    assert response.json()["db"] is True
