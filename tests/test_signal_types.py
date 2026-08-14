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
    NODE_SKIPPED_REASONS,
    DISH_SIGNAL_TYPES,
    PAYLOAD_SHAPES,
    client_emittable_types,
    is_valid,
)

client = TestClient(app)

HEADERS = {"X-Debug-User-Id": "test-user-signal-types"}


# ==============================================================================
# Test 1: Drift guard -- migrations agree with SIGNAL_TYPES
# ==============================================================================

def _extract_signal_types_from_migrations() -> dict[str, str]:
    """Parse all migration SQL files and extract (key, value_kind) from signal_type INSERTs.

    Returns dict mapping signal type key to its SQL value_kind.
    """
    migration_dir = "supabase/migrations"
    types = {}
    insert_pattern = re.compile(r"INSERT INTO signal_type.*?;", re.DOTALL | re.IGNORECASE)
    # Each VALUES row: ('key', 'category', 'value_kind', ...)
    row_pattern = re.compile(
        r"\('([a-z_]+)',\s*'([a-z_]+)',\s*'([a-z_]+)'"
    )

    for path in sorted(glob.glob(f"{migration_dir}/*.sql")):
        with open(path) as f:
            sql = f.read()
        for insert_match in insert_pattern.finditer(sql):
            insert_sql = insert_match.group(0)
            for row_match in row_pattern.finditer(insert_sql):
                key = row_match.group(1)
                value_kind = row_match.group(3)  # skip category (group 2)
                types[key] = value_kind
    return types


def test_drift_guard_migrations_match_python():
    """SPEC-06 core invariant: keys AND value_kind in migrations == SIGNAL_TYPES.

    If this fails, someone added a type to only one place, or changed value_kind
    in one without updating the other. Fix BOTH.
    """
    migration_types = _extract_signal_types_from_migrations()
    migration_keys = set(migration_types.keys())
    python_keys = set(SIGNAL_TYPES.keys())

    # First: key sets must match
    assert migration_keys == python_keys, (
        f"Registry KEY drift detected!\n"
        f"  In migrations only: {migration_keys - python_keys}\n"
        f"  In Python only: {python_keys - migration_keys}"
    )

    # Second: value_kind must agree for every key
    mismatches = []
    for key in python_keys:
        py_vk = SIGNAL_TYPES[key]
        sql_vk = migration_types[key]
        if py_vk != sql_vk:
            mismatches.append(f"  {key}: Python=\'{py_vk}\' vs SQL=\'{sql_vk}\'")

    assert not mismatches, (
        f"Registry VALUE_KIND drift detected!\n" + "\n".join(mismatches)
    )


# ==============================================================================
# Test 2: Each client-emittable type is accepted by ingest
# ==============================================================================

@pytest.mark.parametrize("signal_type", sorted(client_emittable_types()))
def test_client_emittable_types_accepted(signal_type):
    """Each type in client_emittable_types() should be accepted (not rejected)."""
    signal_id = str(uuid.uuid4())
    sig = {
        "signal_id": signal_id,
        "signal_type": signal_type,
        "place_ref": "test-place-001",
        "trip_id": "test-trip-001",
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    # Dish signal types require entity_type='dish' + entity_id (section 29)
    if signal_type in DISH_SIGNAL_TYPES:
        sig["entity_type"] = "dish"
        sig["entity_id"] = "test-dish-001"
    payload = {"signals": [sig]}
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 1, f"{signal_type} was not accepted: {data}"
    assert data["duplicates"] == 0


# ==============================================================================
# Test 3: arrival_delta (server-derived) is rejected from client
# ==============================================================================

def test_arrival_delta_rejected_from_client():
    """Server-derived types cannot be POSTed by clients -- 422-equivalent rejection."""
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


# ==============================================================================
# Test 7: node_skipped reason must be from closed enum
# ==============================================================================

def test_node_skipped_valid_reason_accepted():
    """node_skipped with a valid reason from the closed enum is accepted."""
    import uuid
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [{
            "signal_id": signal_id,
            "signal_type": "node_skipped",
            "place_ref": "test-place-001",
            "trip_id": "test-trip-001",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "value_json": {"reason": "too_tired"},
        }]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1


def test_node_skipped_invalid_reason_rejected():
    """node_skipped with a free-text reason not in the closed enum is rejected."""
    import uuid
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [{
            "signal_id": signal_id,
            "signal_type": "node_skipped",
            "place_ref": "test-place-001",
            "trip_id": "test-trip-001",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "value_json": {"reason": "was tired lol"},
        }]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 0
    assert len(data["rejected"]) == 1
    assert "reason" in data["rejected"][0]["reason"].lower()


def test_node_skipped_reasons_enum_matches_migration():
    """NODE_SKIPPED_REASONS in Python matches enum_values in migration 0004."""
    import re, glob
    # Extract the ARRAY[...] from 0004
    migration_reasons = set()
    for path in sorted(glob.glob("supabase/migrations/0004*.sql")):
        with open(path) as f:
            sql = f.read()
        array_match = re.search(r"ARRAY\[([^\]]+)\]", sql)
        if array_match:
            values = re.findall(r"'([a-z_]+)'", array_match.group(1))
            migration_reasons = set(values)

    assert migration_reasons == NODE_SKIPPED_REASONS, (
        f"node_skipped enum drift!\n"
        f"  Migration only: {migration_reasons - NODE_SKIPPED_REASONS}\n"
        f"  Python only: {NODE_SKIPPED_REASONS - migration_reasons}"
    )


# ==============================================================================
# Test 8: Dish signal types require entity_type='dish' + entity_id (section 29)
# ==============================================================================

def test_dish_loved_with_venue_entity_type_rejected():
    """dish_loved with entity_type='venue' (default) is rejected."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [{
            "signal_id": signal_id,
            "signal_type": "dish_loved",
            "place_ref": "some-restaurant",
            "entity_type": "venue",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 0
    assert len(data["rejected"]) == 1
    assert "entity_type='dish'" in data["rejected"][0]["reason"]


def test_dish_loved_without_entity_id_rejected():
    """dish_loved with entity_type='dish' but no entity_id is rejected."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [{
            "signal_id": signal_id,
            "signal_type": "dish_loved",
            "place_ref": "some-restaurant",
            "entity_type": "dish",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 0
    assert "entity_id" in data["rejected"][0]["reason"]


def test_dish_loved_valid_accepted():
    """dish_loved with entity_type='dish' + entity_id is accepted."""
    signal_id = str(uuid.uuid4())
    payload = {
        "signals": [{
            "signal_id": signal_id,
            "signal_type": "dish_loved",
            "place_ref": "some-restaurant",
            "entity_type": "dish",
            "entity_id": "dish-khao-piak-001",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1


def test_dish_rejected_batch_mates_still_accepted():
    """A bad dish_loved in a batch doesn't kill other valid signals."""
    payload = {
        "signals": [
            {
                "signal_id": str(uuid.uuid4()),
                "signal_type": "dish_loved",
                "place_ref": "restaurant",
                "entity_type": "venue",
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "signal_id": str(uuid.uuid4()),
                "signal_type": "user_loved",
                "place_ref": "dubai-aquarium",
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
    }
    resp = client.post("/api/v1/signals", json=payload, headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 1
    assert len(data["rejected"]) == 1
    assert "dish_loved" in data["rejected"][0]["reason"]


def test_dish_signal_types_subset_of_signal_types():
    """DISH_SIGNAL_TYPES must be a subset of SIGNAL_TYPES keys."""
    assert DISH_SIGNAL_TYPES.issubset(SIGNAL_TYPES.keys())


# ==============================================================================
# Test 9: PAYLOAD_SHAPES documents every signal type
# ==============================================================================

def test_payload_shapes_completeness():
    """Every key in SIGNAL_TYPES must have a PAYLOAD_SHAPES entry.

    Without this, a new signal type can be added to SIGNAL_TYPES + migrations
    and pass the drift guard while silently having no payload documentation.
    """
    missing = set(SIGNAL_TYPES.keys()) - set(PAYLOAD_SHAPES.keys())
    assert not missing, (
        f"PAYLOAD_SHAPES missing documentation for: {sorted(missing)}\n"
        f"Add an entry describing what value_json carries for each."
    )

    extra = set(PAYLOAD_SHAPES.keys()) - set(SIGNAL_TYPES.keys())
    assert not extra, (
        f"PAYLOAD_SHAPES has entries for non-existent types: {sorted(extra)}\n"
        f"Remove stale entries or add the type to SIGNAL_TYPES."
    )
