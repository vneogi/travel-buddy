"""Test configuration and fixtures.

Environment isolation strategy:
- Save real Supabase/JWT creds from .env BEFORE clearing them.
- Clear them globally so the majority of tests run in dev-auth mode
  (X-Debug-User-Id header) without touching a real database.
- Expose the saved values via a `real_supabase_env` fixture that
  test_supabase_integration.py uses to restore them for its scope.

This means:
- test_auth.py + all unit tests: cannot reach a real DB (env is blank).
- test_supabase_integration.py: opts in via the fixture, gets real creds.

History: The global scrubbing was added after a real JWT secret in .env
caused test_auth.py to attempt real JWT validation instead of using the
debug bypass. Do NOT remove the scrubbing — scope it instead.
"""
import os
import sys

# ─── Save real values BEFORE clearing (needed by integration tests) ──────────
_SAVED_SUPABASE_URL = os.environ.get("TB_SUPABASE_URL", "")
_SAVED_SUPABASE_KEY = os.environ.get("TB_SUPABASE_KEY", "")
_SAVED_SUPABASE_JWT_SECRET = os.environ.get("TB_SUPABASE_JWT_SECRET", "")

# ─── MUST run before any app imports ─────────────────────────────────────────
# Override Supabase creds (env vars take precedence over .env file in pydantic).
# Setting to empty string makes Optional[str] fields resolve to None.
os.environ["TB_SUPABASE_JWT_SECRET"] = ""
os.environ["TB_SUPABASE_URL"] = ""
os.environ["TB_SUPABASE_KEY"] = ""
os.environ["TB_DEBUG"] = "true"

# Purge cached config modules so fresh Settings() picks up overrides.
for _mod in list(sys.modules.keys()):
    if _mod.startswith("config"):
        del sys.modules[_mod]
# ─────────────────────────────────────────────────────────────────────────────

import pytest
from fastapi.testclient import TestClient

from main import app
from services.database_service import db_service
from services.cache_service import cache_service


def auth(user_id: str = "test-user-001") -> dict:
    """Return dev-auth headers for a given user_id."""
    return {"X-Debug-User-Id": user_id}


@pytest.fixture(scope="session")
def real_supabase_env():
    """Restore real Supabase env vars for integration tests.

    Used by test_supabase_integration.py. The values were saved before the
    global scrubbing cleared them. Returns a dict; tests should check that
    the URL is non-empty before proceeding (allows the same conftest to work
    on machines without .env configured).
    """
    # Temporarily restore so that importing supabase_service sees real creds.
    old_url = os.environ.get("TB_SUPABASE_URL", "")
    old_key = os.environ.get("TB_SUPABASE_KEY", "")
    os.environ["TB_SUPABASE_URL"] = _SAVED_SUPABASE_URL
    os.environ["TB_SUPABASE_KEY"] = _SAVED_SUPABASE_KEY

    # Purge config cache so Settings() re-reads the restored values.
    for mod in list(sys.modules.keys()):
        if mod.startswith("config"):
            del sys.modules[mod]

    yield {
        "url": _SAVED_SUPABASE_URL,
        "key": _SAVED_SUPABASE_KEY,
        "jwt_secret": _SAVED_SUPABASE_JWT_SECRET,
    }

    # Restore scrubbed state after integration tests finish.
    os.environ["TB_SUPABASE_URL"] = old_url
    os.environ["TB_SUPABASE_KEY"] = old_key
    for mod in list(sys.modules.keys()):
        if mod.startswith("config"):
            del sys.modules[mod]


@pytest.fixture(scope="session", autouse=True)
def _seed_once():
    """Seed venue data once for the test session."""
    from seed_data import seed_venues
    seed_venues()


@pytest.fixture()
def client():
    """Fresh test client per test."""
    return TestClient(app)


@pytest.fixture()
def auth_headers():
    """Dev auth headers for a test user."""
    return {"X-Debug-User-Id": "test-user-001"}


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset in-memory state between tests."""
    yield
    db_service._users.clear()
    db_service._trips.clear()
    db_service._event_log.clear()
    cache_service.clear_all()
