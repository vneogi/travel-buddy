"""SPEC-03 -- Trip party & party_context stamping tests.

Verifies:
1. Create trip WITH explicit party -> persists correctly, returned in response
2. Create trip WITHOUT party -> defaults to solo/1
3. GET /trip/{id} returns the party
4. Signal for a trip with a party gets party_context stamped into value_json
5. Signal for an unknown trip still succeeds (party_context omitted, never fail)
6. Signal with no trip_id still succeeds
7. party_context is MERGED into value_json (doesn't overwrite existing fields)
8. No birth date fields accepted (age_band only)
"""

import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from main import app
from services.database_service import db_service

client = TestClient(app)

DEBUG_USER = "11111111-1111-1111-1111-111111111111"
HEADERS = {"X-Debug-User-Id": DEBUG_USER}


def _now_iso() -> str:
    """Current time as ISO string (for start_date)."""
    return datetime.now(tz=timezone.utc).isoformat()


def _recent_iso(hours_ago: float = 1) -> str:
    """Recent timestamp within skew tolerance (for captured_at)."""
    return (datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)).isoformat()


@pytest.fixture(autouse=True)
def reset_db():
    """Reset in-memory DB between tests."""
    db_service._trips.clear()
    db_service._users.clear()
    db_service._signals.clear()
    db_service._parties.clear()
    yield


def test_create_trip_with_party():
    """Create trip with explicit family party -- persisted and returned."""
    resp = client.post(
        "/api/v1/trip/create",
        json={
            "start_date": _now_iso(),
            "party": {
                "party_type": "daddy_kiddo",
                "size": 2,
                "members": [
                    {"role": "self", "age_band": "adult", "needs": []},
                    {"role": "child", "age_band": "toddler", "needs": ["nap_schedule", "stroller"]},
                ],
            },
        },
        headers=HEADERS,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "party" in data
    party = data["party"]
    assert party["party_type"] == "daddy_kiddo"
    assert party["size"] == 2
    assert len(party["members"]) == 2
    assert party["members"][1]["age_band"] == "toddler"
    assert party["members"][1]["needs"] == ["nap_schedule", "stroller"]


def test_create_trip_without_party_defaults_solo():
    """Create trip with no party field -> defaults to solo, size 1."""
    resp = client.post(
        "/api/v1/trip/create",
        json={
            "start_date": _now_iso(),
        },
        headers=HEADERS,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["party"]["party_type"] == "solo"
    assert data["party"]["size"] == 1
    assert data["party"]["members"] == []


def test_get_trip_includes_party():
    """GET /trip/{id} returns the party for display."""
    # Create a trip with a party
    create_resp = client.post(
        "/api/v1/trip/create",
        json={
            "start_date": _now_iso(),
            "party": {
                "party_type": "couple",
                "size": 2,
                "members": [
                    {"role": "self", "age_band": "adult", "needs": []},
                    {"role": "partner", "age_band": "adult", "needs": []},
                ],
            },
        },
        headers=HEADERS,
    )
    trip_id = create_resp.json()["trip_id"]

    # GET the trip
    get_resp = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS)

    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "party" in data
    assert data["party"]["party_type"] == "couple"
    assert data["party"]["size"] == 2


def test_signal_gets_party_context_stamped():
    """Signal for a trip with a party -> value_json contains party_context.

    This is the MOAT-CRITICAL test: party_context is stamped SERVER-SIDE
    at ingest, merged into value_json.
    """
    # Create trip with family party
    create_resp = client.post(
        "/api/v1/trip/create",
        json={
            "start_date": _now_iso(),
            "party": {
                "party_type": "family_young_kids",
                "size": 4,
                "members": [
                    {"role": "self", "age_band": "adult", "needs": []},
                    {"role": "partner", "age_band": "adult", "needs": []},
                    {"role": "child", "age_band": "toddler", "needs": ["nap_schedule"]},
                    {"role": "child", "age_band": "child", "needs": ["stroller"]},
                ],
            },
        },
        headers=HEADERS,
    )
    trip_id = create_resp.json()["trip_id"]

    # Emit a signal for this trip
    signal_resp = client.post(
        "/api/v1/signals",
        json={
            "signals": [
                {
                    "signal_id": "sig-party-001",
                    "signal_type": "user_loved",
                    "place_ref": "dubai-aquarium",
                    "trip_id": trip_id,
                    "captured_at": _recent_iso(),
                    "value_json": {"original_field": "preserved"},
                }
            ],
        },
        headers=HEADERS,
    )

    assert signal_resp.status_code == 200
    assert signal_resp.json()["accepted"] == 1

    # Verify the stored signal has party_context merged
    stored = db_service.get_signal("sig-party-001")
    assert stored is not None
    vj = stored["value_json"]
    assert "party_context" in vj, f"party_context missing from value_json: {vj}"

    pc = vj["party_context"]
    assert pc["party_type"] == "family_young_kids"
    assert pc["size"] == 4
    assert sorted(pc["age_bands"]) == ["adult", "child", "toddler"]
    # time_of_day is from captured_at (recent, within the hour)
    assert ":" in pc["time_of_day"]  # format HH:MM
    assert "day_index" in pc  # relative to trip start

    # CRITICAL: original value_json fields preserved (merged, not overwritten)
    assert vj["original_field"] == "preserved"


def test_signal_unknown_trip_still_succeeds():
    """Signal for a non-existent trip -> ingest succeeds, no party_context.

    SPEC-03: never fail ingest due to missing party data.
    """
    resp = client.post(
        "/api/v1/signals",
        json={
            "signals": [
                {
                    "signal_id": "sig-unknown-trip",
                    "signal_type": "user_loved",
                    "place_ref": "some-venue",
                    "trip_id": "nonexistent-trip-id",
                    "captured_at": _recent_iso(),
                }
            ],
        },
        headers=HEADERS,
    )

    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1

    # Signal stored, but no party_context
    stored = db_service.get_signal("sig-unknown-trip")
    assert stored is not None
    # value_json should be None or empty (no party_context injected)
    vj = stored["value_json"]
    if vj:
        assert "party_context" not in vj


def test_signal_no_trip_id_still_succeeds():
    """Signal with no trip_id at all -> ingest succeeds, no party_context."""
    resp = client.post(
        "/api/v1/signals",
        json={
            "signals": [
                {
                    "signal_id": "sig-no-trip",
                    "signal_type": "user_loved",
                    "place_ref": "some-venue",
                    "captured_at": _recent_iso(),
                }
            ],
        },
        headers=HEADERS,
    )

    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1


def test_party_context_merge_preserves_existing_value_json():
    """party_context is MERGED into value_json, not overwriting it."""
    # Create trip with solo party
    create_resp = client.post(
        "/api/v1/trip/create",
        json={
            "start_date": _now_iso(),
        },
        headers=HEADERS,
    )
    trip_id = create_resp.json()["trip_id"]

    # Send signal with existing value_json fields
    resp = client.post(
        "/api/v1/signals",
        json={
            "signals": [
                {
                    "signal_id": "sig-merge-test",
                    "signal_type": "user_loved",
                    "place_ref": "test-venue",
                    "trip_id": trip_id,
                    "captured_at": _recent_iso(2),
                    "value_json": {
                        "intensity": 0.9,
                        "source": "heart_button",
                        "nested": {"key": "value"},
                    },
                }
            ],
        },
        headers=HEADERS,
    )

    assert resp.status_code == 200
    stored = db_service.get_signal("sig-merge-test")
    vj = stored["value_json"]

    # Original fields preserved
    assert vj["intensity"] == 0.9
    assert vj["source"] == "heart_button"
    assert vj["nested"] == {"key": "value"}
    # party_context added alongside them
    assert "party_context" in vj
    assert vj["party_context"]["party_type"] == "solo"


def test_no_birth_date_in_party_schema():
    """PartyMemberIn uses age_band only -- no birth_date field accepted.

    Pydantic v2 with default config rejects extra fields (forbid not needed
    since age_band is the spec; just verify the schema has no date fields).
    """
    from models.schemas import PartyMemberIn

    # Check that the model fields do NOT include anything date-like
    fields = PartyMemberIn.model_fields
    date_fields = [f for f in fields if "birth" in f or "date" in f or "dob" in f]
    assert date_fields == [], f"Party schema must not have birth date fields: {date_fields}"

    # Verify age_band IS present
    assert "age_band" in fields
    assert "role" in fields
    assert "needs" in fields
