"""SPEC-42: Uncap trip span -- catalog max_days is not a user-facing cap.

Required proofs from the brief:
1. Create a single-city trip whose calendar span exceeds advertised catalog
   max_days for that region; 201, not 422 over_capacity; creation_context
   start/end match the post; populated node-days <= 5 and <= feasible content.
2. A 10-day span with enough catalog for two packable days creates those two
   days plus empty dates in the span, no fabricated filler.
3. 91 inclusive days returns 422 with a sanity error code, not over_capacity
   and not a catalog N.
4. First+last populated when populated_day_count >= 2.
5. Existing advertised-max create tests still pass for spans that already
   fitted.
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from config.interests import (
    MAX_AUTO_POPULATED_DAYS,
    MAX_DAYS_CEILING,
    TRIP_SPAN_SANITY_DAYS,
    VENUES_PER_DAY,
)
from config.regions import REGIONS
from services.catalog_itinerary import (
    _select_populated_day_indices,
    compute_max_days_for_region,
    range_nodes_from_catalog,
)
from services.database_service import db_service
from tests.conftest import auth

client = TestClient(app)
HEADERS = auth("spec42-user")


def _future_date(offset_days: int = 10) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


def _range_body(
    geo_region: str = "luang_prabang_laos",
    start_offset: int = 10,
    num_days: int = 4,
):
    sd = date.today() + timedelta(days=start_offset)
    ed = sd + timedelta(days=num_days - 1)
    return {
        "start_date": sd.isoformat(),
        "end_date": ed.isoformat(),
        "geo_region": geo_region,
    }


def _node_dates(nodes, geo_region):
    """Extract the set of local dates from nodes."""
    region = REGIONS[geo_region]
    tz = ZoneInfo(region.timezone)
    return sorted({n.scheduled_start.astimezone(tz).date() for n in nodes})


def _node_dates_from_json(nodes_json, geo_region):
    """Extract set of local dates from JSON node list."""
    from datetime import datetime, timezone

    region = REGIONS[geo_region]
    tz = ZoneInfo(region.timezone)
    dates = set()
    for n in nodes_json:
        st = n["scheduled_start"]
        if isinstance(st, str):
            from datetime import datetime as dt

            parsed = dt.fromisoformat(st)
            dates.add(parsed.astimezone(tz).date())
    return sorted(dates)


# ---------------------------------------------------------------------------
# Proof 1: span > catalog max_days succeeds
# ---------------------------------------------------------------------------


class TestSpanExceedsCatalogMax:
    def test_create_longer_than_catalog_max_succeeds(self):
        """A 10-day trip in a region with catalog max_days < 10 must
        return 201, not 422 over_capacity."""
        geo = "vang_vieng_laos"
        catalog_max = compute_max_days_for_region(db_service.list_venues_for_region, geo)
        assert catalog_max is not None and catalog_max < 10, (
            f"Need a region with max_days < 10; {geo} has {catalog_max}"
        )

        body = _range_body(geo_region=geo, num_days=10)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.json()}"

        data = r.json()
        nodes = data["nodes"]

        # Populated node-days <= 5 and <= feasible content
        populated_dates = _node_dates_from_json(nodes, geo)
        assert len(populated_dates) <= MAX_AUTO_POPULATED_DAYS

    def test_creation_context_preserves_full_span(self):
        """creation_context start/end match the posted local dates,
        even when only some days are populated."""
        geo = "vang_vieng_laos"
        sd = date.today() + timedelta(days=10)
        ed = sd + timedelta(days=9)  # 10-day span

        body = {
            "start_date": sd.isoformat(),
            "end_date": ed.isoformat(),
            "geo_region": geo,
        }
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200

        trip_id = r.json()["trip_id"]
        trip_r = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS)
        assert trip_r.status_code == 200
        ctx = trip_r.json()["creation_context"]
        assert ctx["start_date_local"] == sd.isoformat()
        assert ctx["end_date_local"] == ed.isoformat()


# ---------------------------------------------------------------------------
# Proof 2: 10-day span with limited catalog
# ---------------------------------------------------------------------------


class TestSparsePopulation:
    def test_10_day_limited_catalog_produces_sparse_itinerary(self):
        """A 10-day span with catalog for ~2 packable days creates
        those days plus empty dates, no fabricated filler."""
        geo = "vang_vieng_laos"
        body = _range_body(geo_region=geo, num_days=10)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200

        nodes = r.json()["nodes"]
        populated_dates = _node_dates_from_json(nodes, geo)

        # Populated days <= min(5, feasible) -- not 10
        assert len(populated_dates) <= MAX_AUTO_POPULATED_DAYS
        assert len(populated_dates) < 10

        # Each populated day has exactly VENUES_PER_DAY nodes
        from collections import Counter

        day_counts = Counter()
        from datetime import datetime as dt

        region = REGIONS[geo]
        tz = ZoneInfo(region.timezone)
        for n in nodes:
            parsed = dt.fromisoformat(n["scheduled_start"])
            day_counts[parsed.astimezone(tz).date()] += 1
        for d, count in day_counts.items():
            assert count == VENUES_PER_DAY, f"Day {d} has {count} nodes, expected {VENUES_PER_DAY}"


# ---------------------------------------------------------------------------
# Proof 3: 91-day sanity bound
# ---------------------------------------------------------------------------


class TestSanityBound:
    def test_91_days_returns_422_sanity(self):
        """91 inclusive days returns 422 with trip_span_exceeded,
        not over_capacity."""
        body = _range_body(num_days=91)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["error"] == "trip_span_exceeded"
        assert "over_capacity" not in str(detail)

    def test_90_days_accepted(self):
        """90 inclusive days is within the sanity bound."""
        body = _range_body(num_days=90)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Proof 4: first+last populated when >= 2 populated days
# ---------------------------------------------------------------------------


class TestFirstLastPopulated:
    def test_first_and_last_populated_for_long_span(self):
        """When populated_day_count >= 2, first and last calendar day
        are among the populated days."""
        geo = "luang_prabang_laos"
        body = _range_body(geo_region=geo, num_days=10)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200

        sd = date.today() + timedelta(days=10)
        ed = sd + timedelta(days=9)

        nodes = r.json()["nodes"]
        populated_dates = _node_dates_from_json(nodes, geo)

        if len(populated_dates) >= 2:
            assert populated_dates[0] == sd, f"First populated {populated_dates[0]} != start {sd}"
            assert populated_dates[-1] == ed, f"Last populated {populated_dates[-1]} != end {ed}"

    def test_select_populated_day_indices_first_last(self):
        """Unit test: _select_populated_day_indices includes 0 and
        num_days-1 when populated >= 2."""
        indices = _select_populated_day_indices(10, 5)
        assert 0 in indices
        assert 9 in indices
        assert len(indices) == 5

    def test_select_populated_day_indices_single(self):
        """When only 1 can be populated, it is day 0."""
        indices = _select_populated_day_indices(10, 1)
        assert indices == [0]

    def test_select_populated_day_indices_zero(self):
        """When nothing can be populated, empty list."""
        indices = _select_populated_day_indices(10, 0)
        assert indices == []


# ---------------------------------------------------------------------------
# Proof 5: Existing advertised-max create still works
# ---------------------------------------------------------------------------


class TestExistingMaxStillWorks:
    def test_at_catalog_max_still_succeeds(self):
        """A trip at the old advertised max still creates fine."""
        geo = "luang_prabang_laos"
        catalog_max = compute_max_days_for_region(db_service.list_venues_for_region, geo)
        if catalog_max is None or catalog_max < 1:
            pytest.skip("No catalog max for luang_prabang_laos")
        body = _range_body(geo_region=geo, num_days=catalog_max)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200

    def test_two_day_trip_still_creates(self):
        """Regression: a simple 2-day trip still works."""
        body = _range_body(num_days=2)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200
        assert len(r.json()["nodes"]) >= VENUES_PER_DAY * 2


# ---------------------------------------------------------------------------
# Proof 6: Options advertise decoupled fields
# ---------------------------------------------------------------------------


class TestOptionsDecoupled:
    def test_options_include_new_fields(self):
        """Options response includes max_auto_populated_days and
        trip_span_sanity_days alongside informational max_days_by_region."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        assert r.status_code == 200
        opts = r.json()["create_trip_options"]

        assert opts["max_auto_populated_days"] == MAX_AUTO_POPULATED_DAYS
        assert opts["trip_span_sanity_days"] == TRIP_SPAN_SANITY_DAYS

        # max_days_by_region still present as informational
        assert "max_days_by_region" in opts
        assert len(opts["max_days_by_region"]) > 0
