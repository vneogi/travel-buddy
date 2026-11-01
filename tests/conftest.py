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
debug bypass. Do NOT remove the scrubbing -- scope it instead.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# --- Load .env into os.environ FIRST -----------------------------------------
# Without this, os.environ only has shell-exported vars. On most dev machines,
# TB_SUPABASE_URL lives in .env (not exported) -- so os.environ.get() would
# return "" and the integration tests would always skip.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# --- Save real values BEFORE clearing (needed by integration tests) ----------
_SAVED_SUPABASE_URL = os.environ.get("TB_SUPABASE_URL", "")
_SAVED_SUPABASE_KEY = os.environ.get("TB_SUPABASE_KEY", "")
_SAVED_SUPABASE_JWT_SECRET = os.environ.get("TB_SUPABASE_JWT_SECRET", "")

# --- MUST run before any app imports -----------------------------------------
# Override Supabase creds (env vars take precedence over .env file in pydantic).
# Setting to empty string makes Optional[str] fields resolve to None.
os.environ["TB_SUPABASE_JWT_SECRET"] = ""
os.environ["TB_SUPABASE_JWKS_URL"] = ""
os.environ["TB_SUPABASE_JWT_ISS"] = ""
os.environ["TB_SUPABASE_URL"] = ""
os.environ["TB_SUPABASE_KEY"] = ""
os.environ["TB_DEBUG"] = "true"

# Purge cached config modules so fresh Settings() picks up overrides.
for _mod in list(sys.modules.keys()):
    if _mod.startswith("config"):
        del sys.modules[_mod]
# -----------------------------------------------------------------------------

import pytest
from fastapi.testclient import TestClient

from main import app
from monitoring.rate_limit import RateLimitMiddleware
from services.database_service import db_service
from services.cache_service import cache_service

# Suite TestClients share one process IP and often one debug user. Production
# caps (30/identity, 60/IP per minute) would 429 hundreds of existing tests.
# Named Gap 11 rate tests use a private middleware instance, not this one.
_SUITE_RATE_CAP = 1_000_000


def _installed_rate_limiter() -> RateLimitMiddleware | None:
    node = getattr(app, "middleware_stack", None)
    if node is None:
        node = app.build_middleware_stack()
        app.middleware_stack = node
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if isinstance(node, RateLimitMiddleware):
            return node
        node = getattr(node, "app", None)
    return None


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


@pytest.fixture(scope="session", autouse=True)
def _relax_app_rate_limits():
    """Keep the installed limiter from starving the rest of the suite."""
    mw = _installed_rate_limiter()
    if mw is None:
        raise RuntimeError("RateLimitMiddleware is not on the app stack")
    mw.max_identity = _SUITE_RATE_CAP
    mw.max_ip = _SUITE_RATE_CAP
    mw._hits.clear()


@pytest.fixture()
def client():
    """Fresh test client per test."""
    return TestClient(app)


@pytest.fixture()
def auth_headers():
    """Dev auth headers for a test user."""
    return {"X-Debug-User-Id": "test-user-001"}


@pytest.fixture(autouse=True)
def _suite_consent_grant(request, monkeypatch):
    """SPEC-43 Gap 7: grant every purpose for the suite.

    Production has_consent fails closed for optional purposes. Tests marked
    ``real_consent`` skip this grant and exercise the production check.
    """
    if request.node.get_closest_marker("real_consent"):
        yield
        return
    import services.consent as consent

    monkeypatch.setattr(consent, "has_consent", lambda user_id, purpose: True)
    yield


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset in-memory state between tests."""
    yield
    db_service._users.clear()
    db_service._trips.clear()
    db_service._trip_nodes.clear()
    db_service._trip_edges.clear()
    db_service._parties.clear()
    db_service._trip_commands.clear()
    db_service._event_log.clear()
    cache_service.clear_all()
    mw = _installed_rate_limiter()
    if mw is not None:
        mw.max_identity = _SUITE_RATE_CAP
        mw.max_ip = _SUITE_RATE_CAP
        mw._hits.clear()
