"""Nungwi owner field-test pack: a second, separate Zanzibar region.

Owner field-test exception, not the SPEC-13/20 city factory. The Unguja
(zanzibar_tanzania) box already contains Nungwi, so leakage between the two
regions is proven by name sets, not coordinates.

Sabotage proof (R17): make get_bounding_box("nungwi_tanzania") return the
Zanzibar box -> the Nungwi bbox test accepts Stone Town and fails.
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

CATALOG = ROOT / "data" / "nungwi_tanzania.json"
ZANZIBAR_CATALOG = ROOT / "data" / "zanzibar_tanzania.json"
CANDIDATES = ROOT / "docs" / "briefs" / "inputs" / "nungwi_candidates.json"
LAOS_FILES = (
    ROOT / "data" / "laos_luang_prabang.json",
    ROOT / "data" / "laos_vang_vieng.json",
    ROOT / "data" / "laos_vientiane.json",
)
REGION = "nungwi_tanzania"
SIMPLE_HOURS = re.compile(r"^Mo-(Su|Sa) \d\d:\d\d-\d\d:\d\d$")
NUNGWI_DEFAULT = (-5.72720, 39.29920)
STONE_TOWN = (-6.16590, 39.19170)
LAOS_POINT = (19.89758, 102.14321)  # Wat Xieng Thong, Luang Prabang
DUBAI_POINT = (25.1972, 55.2744)


def _venues(path):
    return json.loads(path.read_text(encoding="utf-8"))["venues"]


def _names(path):
    return {v["name"] for v in _venues(path)}


def _laos_names():
    names = set()
    for path in LAOS_FILES:
        names |= _names(path)
    return names


def _inside(box, lat, lng):
    lat_min, lat_max, lng_min, lng_max = box
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def _create(client, user, region):
    created = client.post(
        "/api/v1/trip/create",
        headers=auth(user),
        json={"start_date": "2026-12-28T09:00:00", "geo_region": region},
    )
    assert created.status_code == 200, created.text
    return created.json()


def test_nungwi_region_registered_and_require_region():
    region = require_region(REGION)
    assert region.code == REGION
    assert region.display_name == "Nungwi (Zanzibar)"
    assert region.country == "Tanzania"
    assert region.currency == "TZS"
    assert region.timezone == "Africa/Dar_es_Salaam"
    assert (region.default_lat, region.default_lng) == NUNGWI_DEFAULT
    assert _inside(lv.get_bounding_box(REGION), region.default_lat, region.default_lng)
    assert lv.REGION_CURRENCIES[REGION] == "TZS"
    assert lv.REGION_LANGUAGES[REGION] == "sw"
    # The Stone Town region is still registered and unchanged.
    assert require_region("zanzibar_tanzania").display_name == "Zanzibar"


def test_nungwi_bbox_accepts_nungwi_and_rejects_stone_town_laos_and_dubai_points():
    box = lv.get_bounding_box(REGION)
    assert box == (-5.78, -5.70, 39.27, 39.33)
    kendwa = next(v for v in _venues(CANDIDATES) if v["micro_location"] == "kendwa_south")
    assert _inside(box, *NUNGWI_DEFAULT)
    assert _inside(box, kendwa["lat"], kendwa["lng"])
    assert not _inside(box, *STONE_TOWN)
    assert not _inside(box, *LAOS_POINT)
    assert not _inside(box, *DUBAI_POINT)
    # Other boxes are unchanged; unknown regions still raise.
    assert lv.get_bounding_box("zanzibar_tanzania") == (-6.50, -5.70, 39.10, 39.60)
    assert lv.get_bounding_box("vientiane_laos") == (13.9, 22.6, 100.0, 107.8)
    assert lv.get_bounding_box("dubai_uae") == (24.7, 25.6, 54.8, 55.8)
    with pytest.raises(ValueError):
        lv.get_bounding_box("kendwa_tanzania")
    # Through validate_venue: a Nungwi venue at the Stone Town point is rejected.
    venue = {
        "name": "Bbox probe",
        "description": "probe",
        "category": "cafe",
        "micro_location": "nungwi_village",
        "typical_dwell_minutes": 30,
        "indoor_outdoor": "indoor",
        "price_band": "mid",
    }
    regions = lv.get_all_region_codes()
    ok = lv.validate_venue(
        dict(venue, lat=NUNGWI_DEFAULT[0], lng=NUNGWI_DEFAULT[1]), 0, REGION, regions, set()
    )
    assert ok == []
    bad = lv.validate_venue(
        dict(venue, lat=STONE_TOWN[0], lng=STONE_TOWN[1]), 0, REGION, regions, set()
    )
    assert any("outside bounds" in e for e in bad)


def test_nungwi_catalog_dry_run_and_select_day_venues():
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert payload["geo_region"] == REGION
    regions = lv.get_all_region_codes()
    seen = set()
    errors = []
    for idx, venue in enumerate(payload["venues"]):
        errors += lv.validate_venue(venue, idx, REGION, regions, seen)
    assert errors == []
    vocab = {"nungwi_north_tip", "nungwi_village", "nungwi_beachfront", "kendwa_south"}
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
    assert {r["name"] for r in rows} == _names(CATALOG)
    chosen = select_day_venues(rows)
    assert 4 <= len(chosen) <= 6
    assert {r["name"] for r in chosen} <= _names(CATALOG)


def test_trips_advertise_nungwi_after_zanzibar_when_seeded(client):
    regions = client.get("/api/v1/trips", headers=auth("ng-advertise")).json()["supported_regions"]
    assert REGION in regions
    assert "zanzibar_tanzania" in regions
    assert regions.index(REGION) > regions.index("zanzibar_tanzania")
    assert regions[0] == "dubai_uae"


def test_create_nungwi_uses_catalog_only(client):
    body = _create(client, "ng-create", REGION)
    names = [n["venue_name"] for n in body["nodes"]]
    assert 4 <= len(names) <= 6
    assert set(names) <= _names(CATALOG)
    assert not set(names) & _names(ZANZIBAR_CATALOG)
    assert not set(names) & _laos_names()
    assert not set(names) & DUBAI_FIXTURE_NAMES
    box = lv.get_bounding_box(REGION)
    for node in body["nodes"]:
        assert node["geo_region"] == REGION
        assert node.get("venue_id")
        assert _inside(box, node["lat"], node["lng"]), node["venue_name"]
    fetched = client.get(f"/api/v1/trip/{body['trip_id']}", headers=auth("ng-create")).json()
    assert fetched["geo_region"] == REGION
    assert fetched["current_context"]["location_lat"] == REGIONS[REGION].default_lat
    assert fetched["current_context"]["location_lng"] == REGIONS[REGION].default_lng


def test_create_zanzibar_contains_no_nungwi_venue(client):
    body = _create(client, "ng-zanzibar", "zanzibar_tanzania")
    names = [n["venue_name"] for n in body["nodes"]]
    assert names
    assert not set(names) & _names(CATALOG)
    assert set(names) <= _names(ZANZIBAR_CATALOG)


def test_empty_nungwi_catalog_is_not_advertised(client):
    original = db_service.list_venues_for_region

    def _empty(geo_region: str):
        if geo_region == REGION:
            return []
        return original(geo_region)

    with patch.object(db_service, "list_venues_for_region", side_effect=_empty):
        listed = client.get("/api/v1/trips", headers=auth("ng-empty")).json()
        assert REGION not in listed["supported_regions"]
        assert "zanzibar_tanzania" in listed["supported_regions"]
        response = client.post(
            "/api/v1/trip/create",
            headers=auth("ng-empty"),
            json={"start_date": "2026-12-28T09:00:00", "geo_region": REGION},
        )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "unsupported_region"


def test_nungwi_catalog_matches_candidates_file():
    candidates = _venues(CANDIDATES)
    venues = _venues(CATALOG)
    assert len(candidates) == 34 and len(venues) == 34
    by_name = {v["name"]: v for v in venues}
    assert set(by_name) == {c["name"] for c in candidates}
    for c in candidates:
        v = by_name[c["name"]]
        assert (v["lat"], v["lng"]) == (c["lat"], c["lng"]), c["name"]
        assert v["category"] == c["category_suggestion"], c["name"]
        assert v["micro_location"] == c["micro_location"], c["name"]
        for key in ("dishes", "name_local", "quality_signal", "cuisine_osm"):
            assert key not in v, (c["name"], key)
        assert v["name_local_ref"] == (c["wikidata"] or c["osm_ref"]), c["name"]
        assert v["name_local_source"] == ("wikidata" if c["wikidata"] else "osm"), c["name"]
        assert v["typical_dwell_minutes"] <= 120, c["name"]
        if SIMPLE_HOURS.match(c["opening_hours_osm"] or ""):
            assert isinstance(v["opening_hours"], dict), c["name"]
        else:
            assert v["opening_hours"] is None, c["name"]
    with_hours = {v["name"] for v in venues if v["opening_hours"] is not None}
    assert with_hours == {"Essence Restaurant", "RestOtalia Swahili Restaurant", "The Rocks Spa"}
    text = CATALOG.read_text(encoding="utf-8").lower()
    for claim in ("best", "famous", "hidden gem"):
        assert claim not in text, claim


def test_nungwi_and_zanzibar_catalogs_are_disjoint():
    nungwi, zanzibar = _venues(CATALOG), _venues(ZANZIBAR_CATALOG)
    assert not {v["name"] for v in nungwi} & {v["name"] for v in zanzibar}
    assert not {v["name_local_ref"] for v in nungwi} & {v["name_local_ref"] for v in zanzibar}


def test_seed_language_map_includes_nungwi():
    assert CATALOG_LANGUAGES[REGION] == "sw"
    assert CATALOG_LANGUAGES[REGION] == lv.REGION_LANGUAGES[REGION]
    assert CATALOG_LANGUAGES["zanzibar_tanzania"] == "sw"
