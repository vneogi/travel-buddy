"""Live Supabase integration tests. Skipped unless TB_SUPABASE_URL is set.

Run against a real Supabase project (schema + functions created, venues seeded):
    pytest tests/test_supabase_integration.py -v
Requires: pip install supabase
"""

import os
import uuid
from datetime import datetime

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("TB_SUPABASE_URL"),
    reason="Supabase creds not configured (TB_SUPABASE_URL unset)",
)

from services.supabase_service import get_supabase_service
from models.schemas import TripState, TripNode


@pytest.fixture()
def db():
    svc = get_supabase_service()
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
