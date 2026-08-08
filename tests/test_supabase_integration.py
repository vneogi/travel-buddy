"""Live Supabase integration tests.

Skipped when the user's .env has no TB_SUPABASE_URL (i.e., on CI or a
machine without Supabase configured). On a developer machine with a
populated .env, these run against the real project.

The conftest.py `real_supabase_env` fixture restores the creds that were
scrubbed at test-session startup (to keep test_auth.py isolated).

Run against a real Supabase project (schema + functions created, venues seeded):
    pytest tests/test_supabase_integration.py -v
Requires: pip install supabase
"""

import uuid
from datetime import datetime

import pytest

from tests.conftest import _SAVED_SUPABASE_URL

# Skip the entire module if the .env never had Supabase creds to begin with.
# This check uses the SAVED value (captured before conftest cleared the env).
pytestmark = pytest.mark.skipif(
    not _SAVED_SUPABASE_URL,
    reason="Supabase creds not configured (TB_SUPABASE_URL unset in .env)",
)


@pytest.fixture()
def db(real_supabase_env):
    """Get a live SupabaseService with real credentials restored."""
    # real_supabase_env fixture restores os.environ before this runs.
    # Re-import to get a fresh service with the restored URL/key.
    import importlib
    import services.supabase_service as svc_mod
    importlib.reload(svc_mod)
    svc = svc_mod.get_supabase_service()
    assert svc is not None, "get_supabase_service() returned None despite creds"
    return svc


def test_user_create_roundtrip(db):
    uid = str(uuid.uuid4())  # UUID, since user_tiers.user_id is UUID
    user = db.get_or_create_user(uid)
    assert user.user_id == uid
    assert user.tier_status.value == "free"


def test_trip_persists_across_fetch(db):
    uid = str(uuid.uuid4())
    db.get_or_create_user(uid)  # FK: trip_states.user_id -> user_tiers
    from models.schemas import TripState, TripNode
    trip = TripState(
        user_id=uid,
        nodes=[TripNode(venue_name="Test Venue",
                        scheduled_start=datetime(2026, 8, 5, 9, 0),
                        lat=25.2, lng=55.27)],
    )
    db.save_trip(trip)
    fetched = db.get_trip(trip.trip_id)
    assert fetched is not None
    assert fetched.user_id == uid
    assert fetched.nodes[0].venue_name == "Test Venue"


def test_reroute_quota_is_atomic(db):
    """consume_reroute must never exceed the cap even called in a tight loop."""
    uid = str(uuid.uuid4())
    db.get_or_create_user(uid)
    granted = [db.consume_reroute(uid) for _ in range(7)]  # free cap = 5
    assert sum(1 for g in granted if g is not None) == 5
    assert granted[5] is None and granted[6] is None


def test_venues_were_seeded(db):
    # Requires seed_supabase.py to have been run first.
    assert db.get_venue_count() > 0, "venues_rag is empty -- run seed_supabase.py"


def test_hybrid_search_returns_results(db):
    results = db.hybrid_venue_search(query="quiet premium cafe with great interiors",
                                     user_lat=25.20, user_lng=55.27)
    assert isinstance(results, list)
