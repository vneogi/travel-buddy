"""Zanzibar owner field-test pack: registration, bbox, catalog and create.

This is an owner field-test exception, not the SPEC-13/20 city factory.

Sabotage proof (R17): make get_bounding_box return the Laos box for
zanzibar_tanzania -> the bbox, in-process catalog validation and create-path
bbox assertions fail.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from config.regions import REGIONS, require_region
from seed_data import CATALOG_LANGUAGES
from services.catalog_itinerary import DUBAI_FIXTURE_NAMES, select_day_venues
from services.db_provider import db_service
from tests.conftest import auth

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import load_venues as lv  # noqa: E402

CATALOG = ROOT / "data" / "zanzibar_tanzania.json"
CANDIDATES = ROOT / "docs" / "briefs" / "inputs" / "zanzibar_candidates.json"
LAOS_FILES = (
    ROOT / "data" / "laos_luang_prabang.json",
    ROOT / "data" / "laos_vang_vieng.json",
    ROOT / "data" / "laos_vientiane.json",
)
REGION = "zanzibar_tanzania"
SIMPLE_HOURS = re.compile(r"^Mo-(Su|Sa) \d\d:\d\d-\d\d:\d\d$")
STONE_TOWN = (-6.16590, 39.19170)
LAOS_POINT = (19.89758, 102.14321)  # Wat Xieng Thong, Luang Prabang
DUBAI_POINT = (25.1972, 55.2744)


def _catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _catalog_names():
    return {v["name"] for v in _catalog()["venues"]}


def _laos_names():
    names = set()
    for path in LAOS_FILES:
        names |= {v["name"] for v in json.loads(path.read_text(encoding="utf-8"))["venues"]}
    return names


def _inside(box, lat, lng):
    lat_min, lat_max, lng_min, lng_max = box
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def test_zanzibar_region_registered_and_require_region():
    region = require_region(REGION)
    assert region.code == REGION
    assert region.display_name == "Zanzibar"
    assert region.country == "Tanzania"
    assert region.currency == "TZS"
    assert region.timezone == "Africa/Dar_es_Salaam"
    assert (region.default_lat, region.default_lng) == STONE_TOWN
    assert _inside(lv.get_bounding_box(REGION), region.default_lat, region.default_lng)
    with pytest.raises(KeyError):
        require_region("dar_es_salaam_tanzania")
    assert lv.REGION_CURRENCIES[REGION] == "TZS"
    assert lv.REGION_LANGUAGES[REGION] == "sw"


def test_zanzibar_bbox_accepts_stone_town_and_rejects_laos_and_dubai_points():
    box = lv.get_bounding_box(REGION)
    assert box == (-6.50, -5.70, 39.10, 39.60)
    assert _inside(box, *STONE_TOWN)
    assert not _inside(box, *LAOS_POINT)
    assert not _inside(box, *DUBAI_POINT)
    # Laos and Dubai boxes are unchanged.
    assert lv.get_bounding_box("vientiane_laos") == (13.9, 22.6, 100.0, 107.8)
    assert lv.get_bounding_box("dubai_uae") == (24.7, 25.6, 54.8, 55.8)
    assert not _inside(lv.get_bounding_box("vientiane_laos"), *STONE_TOWN)
    # Through validate_venue: a Zanzibar venue at a Laos point is rejected.
    venue = {
        "name": "Bbox probe",
        "description": "probe",
        "category": "cafe",
        "micro_location": "stone_town",
        "typical_dwell_minutes": 30,
        "indoor_outdoor": "indoor",
        "price_band": "mid",
    }
    regions = lv.get_all_region_codes()
    ok = lv.validate_venue(
        dict(venue, lat=STONE_TOWN[0], lng=STONE_TOWN[1]), 0, REGION, regions, set()
    )
    assert ok == []
    bad = lv.validate_venue(
        dict(venue, lat=LAOS_POINT[0], lng=LAOS_POINT[1]), 0, REGION, regions, set()
    )
    assert any("outside bounds" in e for e in bad)


@pytest.mark.parametrize("code", ["dar_es_salaam_tanzania", "paris_france", "atlantis"])
def test_get_bounding_box_unknown_region_raises(code):
    with pytest.raises(ValueError):
        lv.get_bounding_box(code)
    venue = {
        "name": "Unknown probe",
        "description": "probe",
        "category": "cafe",
        "micro_location": "x",
        "typical_dwell_minutes": 30,
        "indoor_outdoor": "indoor",
        "price_band": "mid",
        "lat": STONE_TOWN[0],
        "lng": STONE_TOWN[1],
    }
    errors = lv.validate_venue(venue, 0, code, frozenset({code}), set())
    assert any("no bounding box" in e for e in errors)


def test_zanzibar_catalog_dry_run_and_select_day_venues():
    payload = _catalog()
    assert payload["geo_region"] == REGION
    regions = lv.get_all_region_codes()
    seen = set()
    errors = []
    for idx, venue in enumerate(payload["venues"]):
        errors += lv.validate_venue(venue, idx, REGION, regions, seen)
    assert errors == []
    vocab = {"stone_town", "forodhani_waterfront", "west_outskirts", "offshore_islets"}
    assert {v["micro_location"] for v in payload["venues"]} <= vocab
    assert CATALOG.read_text(encoding="utf-8").isascii()
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "load_venues.py"), str(CATALOG), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    assert "VALIDATION PASSED" in run.stdout
    rows = db_service.list_venues_for_region(REGION)
    assert {r["name"] for r in rows} == _catalog_names()
    chosen = select_day_venues(rows)
    assert 4 <= len(chosen) <= 6
    assert {r["name"] for r in chosen} <= _catalog_names()


def test_trips_advertise_zanzibar_when_catalog_seeded(client):
    regions = client.get("/api/v1/trips", headers=auth("zz-advertise")).json()["supported_regions"]
    assert REGION in regions
    assert regions[0] == "dubai_uae"
    assert regions.index(REGION) > regions.index("vientiane_laos")


def test_create_zanzibar_uses_catalog_not_dubai_or_laos(client):
    created = client.post(
        "/api/v1/trip/create",
        headers=auth("zz-create"),
        json={"start_date": "2026-12-28T09:00:00", "geo_region": REGION},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    names = [n["venue_name"] for n in body["nodes"]]
    assert 4 <= len(names) <= 6
    assert set(names) <= _catalog_names()
    assert not set(names) & DUBAI_FIXTURE_NAMES
    assert not set(names) & _laos_names()
    box = lv.get_bounding_box(REGION)
    for node in body["nodes"]:
        assert node["geo_region"] == REGION
        assert node.get("venue_id")
        assert _inside(box, node["lat"], node["lng"]), node["venue_name"]
    fetched = client.get(f"/api/v1/trip/{body['trip_id']}", headers=auth("zz-create")).json()
    assert fetched["geo_region"] == REGION
    assert fetched["current_context"]["location_lat"] == REGIONS[REGION].default_lat
    assert fetched["current_context"]["location_lng"] == REGIONS[REGION].default_lng


def test_empty_zanzibar_catalog_is_not_advertised(client):
    original = db_service.list_venues_for_region

    def _empty(geo_region: str):
        if geo_region == REGION:
            return []
        return original(geo_region)

    with patch.object(db_service, "list_venues_for_region", side_effect=_empty):
        listed = client.get("/api/v1/trips", headers=auth("zz-empty")).json()
        assert REGION not in listed["supported_regions"]
        response = client.post(
            "/api/v1/trip/create",
            headers=auth("zz-empty"),
            json={"start_date": "2026-12-28T09:00:00", "geo_region": REGION},
        )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "unsupported_region"


def test_zanzibar_catalog_matches_candidates_file():
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))["venues"]
    venues = _catalog()["venues"]
    assert len(candidates) == 38 and len(venues) == 38
    by_name = {v["name"]: v for v in venues}
    assert set(by_name) == {c["name"] for c in candidates}
    for c in candidates:
        v = by_name[c["name"]]
        assert (v["lat"], v["lng"]) == (c["lat"], c["lng"]), c["name"]
        assert v["category"] == c["category_suggestion"], c["name"]
        assert v["micro_location"] == c["micro_location"], c["name"]
        assert "dishes" not in v and "name_local" not in v, c["name"]
        expected_ref = c["wikidata"] or c["osm_ref"]
        assert v["name_local_ref"] == expected_ref, c["name"]
        assert v["name_local_source"] == ("wikidata" if c["wikidata"] else "osm"), c["name"]
        if not SIMPLE_HOURS.match(c["opening_hours_osm"] or ""):
            assert v["opening_hours"] is None, c["name"]
        else:
            assert isinstance(v["opening_hours"], dict), c["name"]


def test_seed_language_map_matches_loader():
    for region, lang in CATALOG_LANGUAGES.items():
        assert lv.REGION_LANGUAGES[region] == lang
    assert CATALOG_LANGUAGES[REGION] == "sw"
    assert CATALOG_LANGUAGES["luang_prabang_laos"] == "lo"
