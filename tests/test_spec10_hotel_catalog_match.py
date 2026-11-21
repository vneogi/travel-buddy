"""SPEC-10 slice 2 (Amendment 1): title-only hotel edit keeps supplied coords.

Driven through POST /api/v1/trip/event. The catalog is seeded by patching
db_service.list_venues_for_region after trip create, so the real
catalog_coords_for_name exact match runs. No network.
"""

import socket
from pathlib import Path

import pytest

from services.db_provider import db_service
from tests.conftest import auth

GEO = "zanzibar_tanzania"
OLD_ROW = {"name": "Old Inn", "lat": -6.161, "lng": 39.188, "geo_region": GEO}
NEW_ROW = {"name": "New Lodge", "lat": -6.172, "lng": 39.199, "geo_region": GEO}
SUPPLIED = (-6.5, 39.5)
REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def catalog(monkeypatch):
    """Call after trip create: create checks region support via the same call."""
    rows = [OLD_ROW, NEW_ROW]

    def seed():
        monkeypatch.setattr(
            db_service,
            "list_venues_for_region",
            lambda region: [dict(r) for r in rows if r["geo_region"] == region],
        )

    return seed


def _trip(client, user):
    r = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={"geo_region": GEO, "start_date": "2026-12-25", "end_date": "2026-12-27"},
    )
    assert r.status_code == 200, r.text
    return r.json()["trip_id"]


def _add(client, user, trip_id, name, booking_type="hotel", coords=None):
    prefs = {
        "venue_name": name,
        "booking_type": booking_type,
        "scheduled_start": "2026-12-25T15:00:00",
        "duration_minutes": 1200,
        "geo_region": GEO,
    }
    if coords is not None:
        prefs["lat"], prefs["lng"] = coords
    r = client.post(
        "/api/v1/trip/event",
        headers=auth(user),
        json={
            "trip_id": trip_id,
            "event_type": "add_booking",
            "message": "add",
            "preferences": prefs,
        },
    )
    assert r.status_code == 200, r.text
    return next(n for n in r.json()["updated_nodes"] if n["venue_name"] == name)


def _rename(client, user, trip_id, node_id, new_name, **extra):
    prefs = {"venue_name": new_name, **extra}
    r = client.post(
        "/api/v1/trip/event",
        headers=auth(user),
        json={
            "trip_id": trip_id,
            "event_type": "edit_booking",
            "message": "edit",
            "target_node_id": node_id,
            "preferences": prefs,
        },
    )
    assert r.status_code == 200, r.text
    return next(n for n in r.json()["updated_nodes"] if n["node_id"] == node_id)


def _coords(node):
    return (node["lat"], node["lng"])


def test_title_edit_keeps_supplied_coords_when_old_name_has_no_row(client, catalog):
    trip_id = _trip(client, "hcm-1")
    catalog()
    hotel = _add(client, "hcm-1", trip_id, "Pin Hotel", coords=SUPPLIED)
    assert _coords(hotel) == SUPPLIED
    edited = _rename(client, "hcm-1", trip_id, hotel["node_id"], "New Lodge")
    assert _coords(edited) == SUPPLIED


def test_title_edit_keeps_supplied_coords_that_differ_from_old_row(client, catalog):
    trip_id = _trip(client, "hcm-2")
    catalog()
    hotel = _add(client, "hcm-2", trip_id, "Old Inn", coords=SUPPLIED)
    assert _coords(hotel) == SUPPLIED  # supplied, not the catalog row
    edited = _rename(client, "hcm-2", trip_id, hotel["node_id"], "New Lodge")
    assert _coords(edited) == SUPPLIED


def test_title_edit_re_resolves_catalog_filled_hotel(client, catalog):
    trip_id = _trip(client, "hcm-3")
    catalog()
    hotel = _add(client, "hcm-3", trip_id, "Old Inn")
    assert _coords(hotel) == (OLD_ROW["lat"], OLD_ROW["lng"])
    edited = _rename(client, "hcm-3", trip_id, hotel["node_id"], "New Lodge")
    assert _coords(edited) == (NEW_ROW["lat"], NEW_ROW["lng"])


def test_title_edit_clears_catalog_filled_coords_when_new_name_misses(client, catalog):
    trip_id = _trip(client, "hcm-4")
    catalog()
    hotel = _add(client, "hcm-4", trip_id, "Old Inn")
    assert _coords(hotel) == (OLD_ROW["lat"], OLD_ROW["lng"])
    edited = _rename(client, "hcm-4", trip_id, hotel["node_id"], "Nowhere Stay")
    assert _coords(edited) == (None, None)


def test_city_change_behaviour_is_covered_by_existing_test():
    # Pointer, not a duplicate: city change still clears old-city coords and
    # re-resolves (B7), proven by the existing test named below.
    src = (REPO / "tests" / "test_g0_field_fix_proofs.py").read_text(encoding="utf-8")
    assert "def test_edit_city_change_clears_old_coords(" in src


def test_flight_title_edit_never_gains_or_loses_coords(client, catalog):
    trip_id = _trip(client, "hcm-6")
    catalog()
    with_coords = _add(client, "hcm-6", trip_id, "Flight A", booking_type="flight", coords=SUPPLIED)
    edited = _rename(client, "hcm-6", trip_id, with_coords["node_id"], "Old Inn")
    assert _coords(edited) == SUPPLIED
    bare = _add(client, "hcm-6", trip_id, "Flight B", booking_type="flight")
    assert _coords(bare) == (None, None)
    edited = _rename(client, "hcm-6", trip_id, bare["node_id"], "New Lodge")
    assert _coords(edited) == (None, None)


def test_catalog_error_during_edit_keeps_coords(client, catalog, monkeypatch):
    trip_id = _trip(client, "hcm-7")
    catalog()
    hotel = _add(client, "hcm-7", trip_id, "Old Inn")
    assert _coords(hotel) == (OLD_ROW["lat"], OLD_ROW["lng"])

    def _boom(region):
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(db_service, "list_venues_for_region", _boom)
    edited = _rename(client, "hcm-7", trip_id, hotel["node_id"], "New Lodge")
    assert _coords(edited) == (OLD_ROW["lat"], OLD_ROW["lng"])


def test_edit_path_makes_no_network_call(client, catalog, monkeypatch):
    trip_id = _trip(client, "hcm-8")
    catalog()
    hotel = _add(client, "hcm-8", trip_id, "Old Inn")

    def _blocked(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    edited = _rename(client, "hcm-8", trip_id, hotel["node_id"], "New Lodge")
    assert _coords(edited) == (NEW_ROW["lat"], NEW_ROW["lng"])
