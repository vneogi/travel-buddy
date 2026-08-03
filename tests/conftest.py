import pytest
from fastapi.testclient import TestClient

from main import app
from services.database_service import db_service
from services.cache_service import cache_service


@pytest.fixture(scope="session", autouse=True)
def _seed_once():
    """Seed venues once for the whole session."""
    from seed_data import seed_venues
    if db_service.get_venue_count() == 0:
        seed_venues()


@pytest.fixture(autouse=True)
def _reset_state():
    """Isolate tests: clear per-user/trip/event state + cache before each test."""
    db_service._users.clear()
    db_service._trips.clear()
    db_service._event_log.clear()
    cache_service.clear_all()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def auth(user_id: str) -> dict:
    """Dev-mode auth header (no JWT secret configured in tests)."""
    return {"X-Debug-User-Id": user_id}
