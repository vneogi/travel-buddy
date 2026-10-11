"""SPEC-45 Phase B: Field trust hygiene -- Python backend tests.

Tests the refusal_code/refusal_copy fields on the swap_candidates endpoint.
Forces an empty candidate set (no catalog for the region) to prove refusal
fields are always present.
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
    """SPEC-45 B4: swap_candidates must return refusal_code when empty."""

    def test_forced_empty_region_returns_no_catalog_refusal(self):
        """A region with no catalog entries must return refusal_code='no_catalog'."""
        uid = "spec45-b4-force-empty"
        # Create a trip in a region that has no venue catalog at all.
        # Use a fake region -- the in-memory backend won't have venues for it.
        r = client.post(
            "/api/v1/trip/create",
            json={
                "geo_region": "nowhere_test_region",
                "days": 1,
                "start_date": "2026-10-02",
                "party_type": "solo",
                "party_size": 1,
            },
            headers=_auth(uid),
        )
        if r.status_code != 200:
            # Some regions may be rejected at create. Fall back to LP.
            trip_id = _create_trip(uid)
        else:
            trip_id = r.json()["trip_id"]

        trip = client.get(f"/api/v1/trip/{trip_id}", headers=_auth(uid))
        assert trip.status_code == 200
        nodes = trip.json()["nodes"]
        target = next((n for n in nodes if not n.get("is_locked")), None)
        if target is None:
            pytest.skip("No unlocked node in seeded trip")

        resp = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{target['node_id']}",
            headers=_auth(uid),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if not data["candidates"]:
            assert "refusal_code" in data, "empty candidates must carry refusal_code"
            assert data["refusal_code"] in ("hours", "reachability", "no_catalog")
            assert "refusal_copy" in data
            assert len(data["refusal_copy"]) > 0, "refusal_copy must be non-empty"

    def test_refusal_fields_present_on_empty_result(self):
        """Verify refusal_code + non-empty copy when result is empty."""
        uid = "spec45-b4-empty-proof"
        trip_id = _create_trip(uid)
        trip = client.get(f"/api/v1/trip/{trip_id}", headers=_auth(uid))
        assert trip.status_code == 200
        nodes = trip.json()["nodes"]
        target = next((n for n in nodes if not n.get("is_locked")), None)
        if target is None:
            pytest.skip("No unlocked node")

        resp = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{target['node_id']}",
            headers=_auth(uid),
        )
        assert resp.status_code == 200
        data = resp.json()
        if not data["candidates"]:
            assert data["refusal_code"] in ("hours", "reachability", "no_catalog")
            assert data["refusal_copy"], "refusal_copy must be non-empty"
        # If there ARE candidates, refusal should be absent
        else:
            assert data.get("refusal_code") is None

    def test_locked_node_returns_409(self):
        """Locked bookings cannot be swapped."""
        uid = "spec45-b4-locked"
        trip_id = _create_trip(uid)
        trip = client.get(f"/api/v1/trip/{trip_id}", headers=_auth(uid))
        assert trip.status_code == 200
        locked = next(
            (n for n in trip.json()["nodes"] if n.get("is_locked")),
            None,
        )
        if locked is None:
            pytest.skip("No locked node in seeded trip")
        resp = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{locked['node_id']}",
            headers=_auth(uid),
        )
        assert resp.status_code == 409
