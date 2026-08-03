"""Test configuration and fixtures.

Environment isolation: overrides Supabase creds in env so the app stays in
dev-auth mode (X-Debug-User-Id) during tests. This ensures tests pass
regardless of what's in the developer's .env file.

IMPORTANT: The .env file is still read by pydantic-settings, but env vars
take precedence over .env values. Setting them to empty string here ensures
the app sees them as unset/None.
"""
import os
import sys

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
