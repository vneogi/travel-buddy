"""SPEC-05 Observability tests.

Covers: unhandled exceptions, validation errors, debug endpoint gating,
secret-leak prevention, ring buffer cap, and X-Request-ID header.
"""
import pytest
from fastapi.testclient import TestClient
from fastapi import APIRouter

from main import app
from monitoring.error_log import error_log
from config.settings import settings
from tests.conftest import auth


# ---------------------------------------------------------------------------
# Fixture: register a temporary crash route for testing (never ships)
# ---------------------------------------------------------------------------

_test_router = APIRouter()


@_test_router.get("/api/v1/_test/crash")
async def _crash_endpoint():
    """Deliberately raises to test the exception handler."""
    raise RuntimeError("Deliberate test crash")


# Mount once (idempotent — FastAPI won't double-register the same path)
app.include_router(_test_router)


@pytest.fixture(autouse=True)
def _clear_error_log():
    """Start each test with a clean ring buffer."""
    error_log.clear()
    yield
    error_log.clear()


# ---------------------------------------------------------------------------
# Test 1: Unhandled exception -> 500 + request_id + entry in ring buffer
# ---------------------------------------------------------------------------

def test_unhandled_exception_returns_500_with_request_id():
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/v1/_test/crash")
    assert r.status_code == 500
    body = r.json()
    assert "request_id" in body
    assert body["detail"] == "Internal server error"
    # Ring buffer should have an entry
    entries = error_log.recent(limit=1)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["exc_type"] == "RuntimeError"
    assert "Deliberate test crash" in entry["message"]
    assert entry["traceback"] != ""  # Full traceback captured
    assert entry["status"] == 500


# ---------------------------------------------------------------------------
# Test 2: Validation error -> 422 + entry recorded
# ---------------------------------------------------------------------------

def test_validation_error_returns_422_with_entry():
    client = TestClient(app, raise_server_exceptions=False)
    # POST /api/v1/signals with invalid body (missing required fields)
    r = client.post(
        "/api/v1/signals",
        json={"not_a_real_field": "garbage"},
        headers=auth("test-user-validation"),
    )
    assert r.status_code == 422
    body = r.json()
    assert "request_id" in body
    # Ring buffer should have a validation entry
    entries = error_log.recent(limit=1)
    assert len(entries) == 1
    assert entries[0]["exc_type"] == "RequestValidationError"
    assert entries[0]["status"] == 422


# ---------------------------------------------------------------------------
# Test 3: GET /debug/errors returns entries when debug=True
# ---------------------------------------------------------------------------

def test_debug_errors_returns_200_when_debug_on():
    client = TestClient(app, raise_server_exceptions=False)
    # Trigger a crash first
    client.get("/api/v1/_test/crash")
    # Now check the debug endpoint
    r = client.get("/api/v1/debug/errors")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert len(body["errors"]) >= 1
    assert body["errors"][0]["exc_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# Test 4: GET /debug/errors returns 404 when debug=False
# ---------------------------------------------------------------------------

def test_debug_errors_returns_404_when_debug_off(monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(settings, "debug", False)
    r = client.get("/api/v1/debug/errors")
    assert r.status_code == 404
    # Restore for other tests
    monkeypatch.setattr(settings, "debug", True)


# ---------------------------------------------------------------------------
# Test 5: Secret-leak guard — no env values in error log
# ---------------------------------------------------------------------------

def test_no_secrets_in_error_log(monkeypatch):
    """Set a fake API key, trigger an error, assert the key never leaks."""
    fake_secret = "sk-test-SUPER-SECRET-12345"
    monkeypatch.setattr(settings, "litellm_api_key", fake_secret)

    client = TestClient(app, raise_server_exceptions=False)
    client.get("/api/v1/_test/crash")

    entries = error_log.recent(limit=10)
    # Serialize all entries to string and check for the secret
    import json
    all_text = json.dumps(entries)
    assert fake_secret not in all_text, "Secret leaked into error log!"


# ---------------------------------------------------------------------------
# Test 6: Ring buffer capped at 100
# ---------------------------------------------------------------------------

def test_ring_buffer_capped_at_100():
    for i in range(150):
        error_log.record(
            request_id=f"req-{i}",
            method="GET",
            path="/test",
            status=500,
            exc_type="TestError",
            message=f"Error {i}",
        )
    assert error_log.count() == 100
    # Most recent should be the last one recorded
    recent = error_log.recent(limit=1)
    assert recent[0]["request_id"] == "req-149"


# ---------------------------------------------------------------------------
# Test 7: X-Request-ID header present on normal responses
# ---------------------------------------------------------------------------

def test_request_id_header_on_normal_response():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) == 12  # uuid hex[:12]
