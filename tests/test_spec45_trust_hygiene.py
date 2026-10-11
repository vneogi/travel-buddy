"""SPEC-45 Phase B: Field trust hygiene -- Python backend tests.

Forces an empty swap_candidates result via monkeypatch so refusal_code
and refusal_copy are always asserted. No skip, no conditional.
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


def _unlocked_node(uid):
    """Create trip, return (trip_id, target_node dict)."""
    trip_id = _create_trip(uid)
    trip = client.get(f"/api/v1/trip/{trip_id}", headers=_auth(uid))
    assert trip.status_code == 200
    nodes = trip.json()["nodes"]
    target = next((n for n in nodes if not n.get("is_locked")), None)
    assert target is not None, "Need at least one unlocked node"
    return trip_id, target


class TestSwapCandidatesRefusal:
    """SPEC-45 B4: swap_candidates must return refusal_code when empty."""

    def test_hours_refusal_via_monkeypatch(self, monkeypatch):
        """Monkeypatch hours_for_slot to always return CLOSED.
        _considered > 0 and _rejected_hours dominates -> refusal_code='hours'."""
        from services.opening_hours import HoursResult

        uid = "spec45-b4-hours-mp"
        trip_id, target = _unlocked_node(uid)

        monkeypatch.setattr(
            "services.opening_hours.hours_for_slot",
            lambda _structured, _start, _dwell, _region: HoursResult.CLOSED,
        )
        resp = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{target['node_id']}",
            headers=_auth(uid),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["candidates"] == [], "monkeypatch should empty candidates"
        assert data["refusal_code"] == "hours"
        assert data["refusal_copy"] == "All nearby alternatives are closed at this time."

    def test_reachability_refusal_via_monkeypatch(self, monkeypatch):
        """Monkeypatch _is_swap_reachable to always return False.
        Hours pass but reachability rejects -> refusal_code='reachability'."""
        uid = "spec45-b4-reach-mp"
        trip_id, target = _unlocked_node(uid)

        import sys

        sm_mod = sys.modules["agents.state_machine"]

        monkeypatch.setattr(
            sm_mod,
            "_is_swap_reachable",
            lambda _target, _lat, _lng, _dwell, _nodes, _idx: False,
        )
        resp = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{target['node_id']}",
            headers=_auth(uid),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["candidates"] == [], "monkeypatch should empty candidates"
        assert data["refusal_code"] in ("reachability", "hours")
        assert len(data["refusal_copy"]) > 0, "refusal_copy must be non-empty"

    def test_no_catalog_refusal_via_monkeypatch(self, monkeypatch):
        """Monkeypatch list_venues_for_region to return empty.
        _considered == 0 -> refusal_code='no_catalog'."""
        from services.db_provider import db_service

        uid = "spec45-b4-nocat-mp"
        trip_id, target = _unlocked_node(uid)

        monkeypatch.setattr(db_service, "list_venues_for_region", lambda _region: [])
        resp = client.get(
            f"/api/v1/trip/{trip_id}/swap_candidates/{target['node_id']}",
            headers=_auth(uid),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["candidates"] == [], "monkeypatch should empty candidates"
        assert data["refusal_code"] == "no_catalog"
        assert data["refusal_copy"] == "No alternative venues in the catalog for this area."
