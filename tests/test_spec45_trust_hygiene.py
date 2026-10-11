"""SPEC-45 Phase B: Field trust hygiene -- Python backend tests.

Tests the refusal_code/refusal_copy fields on the swap_candidates endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _auth(uid: str) -> dict:
    return {"X-Debug-User-Id": uid}


def _create_trip(uid: str, region: str = "luang_prabang_laos") -> str:
    r = client.post(
        "/api/v1/trip/create",
        json={
            "geo_region": region,
            "days": 1,
            "start_date": "2026-10-02",
            "party_type": "solo",
            "party_size": 1,
        },
        headers=_auth(uid),
    )
    assert r.status_code == 200, r.text
    return r.json()["trip_id"]


class TestSwapCandidatesRefusal:
    """SPEC-45 B4: swap_candidates response includes refusal_code when empty."""

    def test_empty_candidates_include_refusal_fields(self):
        """When no candidates survive filtering, the response must carry
        refusal_code and refusal_copy."""
        uid = "spec45-b4-refusal"
        trip_id = _create_trip(uid)
        trip = client.get(f"/api/v1/trip/{trip_id}", headers=_auth(uid))
        assert trip.status_code == 200
        nodes = trip.json()["nodes"]
        target = next((n for n in nodes if not n.get("is_locked")), None)
        if target is None:
            pytest.skip("No unlocked node in seeded trip")

        r = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{target['node_id']}",
            headers=_auth(uid),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if not data["candidates"]:
            assert "refusal_code" in data, "empty candidates must carry refusal_code"
            assert data["refusal_code"] in ("hours", "reachability", "no_catalog")
            assert "refusal_copy" in data
            assert len(data["refusal_copy"]) > 0
        else:
            # If candidates exist, refusal fields should be absent
            assert data.get("refusal_code") is None

    def test_locked_node_returns_409(self):
        """Locked bookings cannot be swapped -- 409 from the endpoint."""
        uid = "spec45-b4-locked"
        trip_id = _create_trip(uid)
        trip = client.get(f"/api/v1/trip/{trip_id}", headers=_auth(uid))
        assert trip.status_code == 200
        nodes = trip.json()["nodes"]
        locked = next((n for n in nodes if n.get("is_locked")), None)
        if locked is None:
            pytest.skip("No locked node in seeded trip")

        r = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{locked['node_id']}",
            headers=_auth(uid),
        )
        assert r.status_code == 409
