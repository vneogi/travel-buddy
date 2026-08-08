"""SPEC-06: Signal type registry tests.

These tests enforce that models/signal_types.py (the single source of truth)
stays in sync with the Supabase migrations, and that the ingest endpoint
correctly accepts/rejects each type.

Per ENGINEERING_RULES.md R5: one registry, one source of truth.
"""

import glob
import re
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from models.signal_types import (
    SIGNAL_TYPES,
    SERVER_DERIVED_TYPES,
    client_emittable_types,
    is_valid,
)

client = TestClient(app)

HEADERS = {"X-Debug-User-Id": "test-user-signal-types"}


# ==============================================================================
# Test 1: Drift guard — migrations agree with SIGNAL_TYPES
# ==============================================================================

def _extract_signal_type_keys_from_migrations() -> set:
    """Parse all migration SQL files and extract keys inserted into signal_type."""
    migration_dir = "supabase/migrations"
    keys = set()
    # Match patterns like: ('user_loved', ...) or ('reroute_accepted', ...)
    # in INSERT INTO signal_type statements
    pattern = re.compile(r"INSERT INTO signal_type.*?;", re.DOTALL | re.IGNORECASE)
    key_pattern = re.compile(r"\('([a-z_]+)',")

    for path in sorted(glob.glob(f"{migration_dir}/*.sql")):
        with open(path) as f:
            sql = f.read()
        for insert_match in pattern.finditer(sql):
            insert_sql = insert_match.group(0)
            for key_match in key_pattern.finditer(insert_sql):
                keys.add(key_match.group(1))
    return keys


def test_drift_guard_migrations_match_python():
    """SPEC-06 core invariant: the set of keys in migrations == SIGNAL_TYPES keys.

    If this fails, someone added a type to only one place. Fix BOTH.
    """
    migration_keys = _extract_signal_type_keys_from_migrations()
    python_keys = set(SIGNAL_TYPES.keys())
    assert migration_keys == python_keys, (
        f"Registry drift detected!\n"
        f"  In migrations only: {migration_keys - python_keys}\n"
        f"  In Python only: {python_keys - migration_keys}"
    )


# ==============================================================================
# Test 2: Each client-emittable type is accepted by ingest
# ==============================================================================

@pytest.mark.parametrize("signal_type", sorted(client_emittable_types()))
def test_client_emittable_types_accepted(signal_type):
    """Each type in client_emittable_types() should be accepted (not rejected)."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [{
            "signal_id": signal_id,
            "signal_type": signal_type,
            "place_ref": "test-place-001",
            "trip_id": "test-trip-001",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 1, f"{signal_type} was not accepted: {data}"
    assert data["duplicates"] == 0


# ==============================================================================
# Test 3: arrival_delta (server-derived) is rejected from client
# ==============================================================================

def test_arrival_delta_rejected_from_client():
    """Server-derived types cannot be POSTed by clients — 422-equivalent rejection."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [{
            "signal_id": signal_id,
            "signal_type": "arrival_delta",
            "place_ref": "test-place-001",
            "trip_id": "test-trip-001",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "value_json": {"minutes": 5},
        }]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 0
    assert len(data["rejected"]) == 1
    assert "server-side" in data["rejected"][0]["reason"]


# ==============================================================================
# Test 4: Unregistered type is rejected
# ==============================================================================

def test_unregistered_type_rejected():
    """An unknown signal type gets per-item rejected (not a 500)."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [{
            "signal_id": signal_id,
            "signal_type": "bogus_type",
            "place_ref": "test-place-001",
            "trip_id": "test-trip-001",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 0
    assert len(data["rejected"]) == 1
    assert "unknown signal_type" in data["rejected"][0]["reason"]


# ==============================================================================
# Test 5: Both backends agree on valid types
# ==============================================================================

def test_both_backends_agree():
    """database_service and signal_types module expose identical type sets."""
    from services.database_service import db_service
    backend_types = db_service.get_valid_signal_types()
    python_types = set(SIGNAL_TYPES.keys())
    assert backend_types == python_types


# ==============================================================================
# Test 6: is_valid and client_emittable_types are consistent
# ==============================================================================

def test_is_valid_covers_all():
    """is_valid returns True for every key in SIGNAL_TYPES."""
    for key in SIGNAL_TYPES:
        assert is_valid(key), f"is_valid('{key}') returned False"
    assert not is_valid("nonexistent_type")


def test_server_derived_not_in_client_emittable():
    """SERVER_DERIVED_TYPES are excluded from client_emittable_types."""
    emittable = client_emittable_types()
    for t in SERVER_DERIVED_TYPES:
        assert t not in emittable, f"{t} should not be client-emittable"
        assert t in SIGNAL_TYPES, f"{t} must still be in SIGNAL_TYPES"
