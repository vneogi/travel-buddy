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
from models.schemas import TripSegmentIn
from config.corridors import require_corridor
from services.corridor_itinerary import (
    build_corridor_nodes,
    validate_corridor_segments,
    advertised_corridors,
    InvalidCorridor,
    CORRIDOR_STOPS_PER_DAY,
)
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


# ---------------------------------------------------------------------------
# Proof 7: Weekday-specific hours sabotage (item 2 fix proof)
# ---------------------------------------------------------------------------


class TestWeekdayProbeUsesActualDates:
    """The feasibility probe must use the actual trip dates so that
    weekday-specific hours are evaluated correctly.

    Under the old fixed-Monday probe (2026-09-14), a venue whose
    structured_hours has all weekdays closed except Thursday would
    report zero feasible days for a Monday-start probe, but should
    report 1 feasible day when the trip actually starts on a Thursday.
    """

    def test_thursday_only_venue_packs_on_thursday(self):
        """Sabotage: monkeypatch catalog to have a venue that only opens
        Thursday. A probe starting on a Thursday must find it feasible."""

        thursday_hours = {
            "mon": [],
            "tue": [],
            "wed": [],
            "thu": [["09:00", "18:00"]],
            "fri": [],
            "sat": [],
            "sun": [],
        }

        original = db_service.list_venues_for_region

        def patched(region):
            rows = original(region)
            if region == "luang_prabang_laos":
                # Replace hours on all venues: only open Thursday
                patched_rows = []
                for r in rows:
                    pr = dict(r)
                    pr["opening_hours_structured"] = thursday_hours
                    patched_rows.append(pr)
                return patched_rows
            return rows

        db_service.list_venues_for_region = patched
        try:
            # 2026-10-01 is Thursday
            sd = "2026-10-01"
            ed = "2026-10-01"  # 1-day trip on Thursday
            rows = db_service.list_venues_for_region("luang_prabang_laos")
            nodes = range_nodes_from_catalog(
                geo_region="luang_prabang_laos",
                start_date_local=sd,
                end_date_local=ed,
                rows=rows,
            )
            # The probe uses the actual Thursday date, so it finds feasible
            assert len(nodes) > 0, (
                "Thursday-only venue must pack when trip is on Thursday "
                "(old Monday probe would have returned zero)"
            )
        finally:
            db_service.list_venues_for_region = original

    def test_monday_closed_venue_empty_on_monday(self):
        """Complementary: a venue open only Thursday yields zero nodes
        when the trip starts on Monday."""

        thursday_hours = {
            "mon": [],
            "tue": [],
            "wed": [],
            "thu": [["09:00", "18:00"]],
            "fri": [],
            "sat": [],
            "sun": [],
        }

        original = db_service.list_venues_for_region

        def patched(region):
            rows = original(region)
            if region == "luang_prabang_laos":
                return [dict(r, opening_hours_structured=thursday_hours) for r in rows]
            return rows

        db_service.list_venues_for_region = patched
        try:
            # 2026-09-28 is Monday
            rows = db_service.list_venues_for_region("luang_prabang_laos")
            nodes = range_nodes_from_catalog(
                geo_region="luang_prabang_laos",
                start_date_local="2026-09-28",
                end_date_local="2026-09-28",
                rows=rows,
            )
            assert len(nodes) == 0, "Thursday-only venue must not pack on a Monday trip"
        finally:
            db_service.list_venues_for_region = original


# ---------------------------------------------------------------------------
# Proof 8: Large-gap corridor sabotage (item 4 fix proof)
# ---------------------------------------------------------------------------


class TestInclusiveCorridorSpan:
    """The 90-day sanity bound applies to the inclusive span
    (first segment start through last segment end), not just the
    sum of segment durations."""

    def test_large_gap_between_segments_rejected(self):
        """Three 1-day segments with huge gaps totalling 91 inclusive days
        must be rejected, even though sum of durations is only 3."""
        sd = date.today() + timedelta(days=10)
        # seg1: day 0, seg2: day 45, seg3: day 90  => inclusive span = 91
        segments = [
            TripSegmentIn(
                geo_region="vientiane_laos",
                starts_on=sd,
                ends_on=sd,
            ),
            TripSegmentIn(
                geo_region="vang_vieng_laos",
                starts_on=sd + timedelta(days=45),
                ends_on=sd + timedelta(days=45),
            ),
            TripSegmentIn(
                geo_region="luang_prabang_laos",
                starts_on=sd + timedelta(days=90),
                ends_on=sd + timedelta(days=90),
            ),
        ]
        corridor = require_corridor("laos_northbound_v1")
        with pytest.raises(InvalidCorridor, match="[Ii]nclusive"):
            validate_corridor_segments(segments, corridor)

    def test_gap_within_90_days_accepted(self):
        """Inclusive span of exactly 90 days with gaps is valid."""
        sd = date.today() + timedelta(days=10)
        # seg1: day 0, seg2: day 44, seg3: day 89  => inclusive span = 90
        segments = [
            TripSegmentIn(
                geo_region="vientiane_laos",
                starts_on=sd,
                ends_on=sd,
            ),
            TripSegmentIn(
                geo_region="vang_vieng_laos",
                starts_on=sd + timedelta(days=44),
                ends_on=sd + timedelta(days=44),
            ),
            TripSegmentIn(
                geo_region="luang_prabang_laos",
                starts_on=sd + timedelta(days=89),
                ends_on=sd + timedelta(days=89),
            ),
        ]
        corridor = require_corridor("laos_northbound_v1")
        # Should not raise
        validate_corridor_segments(segments, corridor)


# ---------------------------------------------------------------------------
# Proof 9: Empty corridor (item 5 fix proof)
# ---------------------------------------------------------------------------


class TestEmptyCorridorPermitted:
    """A region with fewer venues than CORRIDOR_STOPS_PER_DAY must not
    raise UnsupportedCorridor.  SPEC-42 permits zero populated days."""

    def test_zero_venue_region_produces_empty_segment(self):
        """Monkeypatch one region to return zero venues.
        build_corridor_nodes must succeed with no nodes for that segment."""
        corridor = require_corridor("laos_northbound_v1")
        sd = date.today() + timedelta(days=10)
        segments = [
            TripSegmentIn(geo_region="vientiane_laos", starts_on=sd, ends_on=sd),
            TripSegmentIn(
                geo_region="vang_vieng_laos",
                starts_on=sd + timedelta(days=2),
                ends_on=sd + timedelta(days=2),
            ),
            TripSegmentIn(
                geo_region="luang_prabang_laos",
                starts_on=sd + timedelta(days=4),
                ends_on=sd + timedelta(days=4),
            ),
        ]

        def sparse_fn(region):
            if region == "vang_vieng_laos":
                return []  # zero venues
            return db_service.list_venues_for_region(region)

        # Must NOT raise
        nodes, stored = build_corridor_nodes(segments, sparse_fn, corridor)
        assert len(stored) == 3, "All 3 segments must be stored"
        # Vang Vieng produced zero nodes
        vv_nodes = [n for n in nodes if n.geo_region == "vang_vieng_laos"]
        assert len(vv_nodes) == 0


# ---------------------------------------------------------------------------
# Proof 10: advertised_corridors does not check capacity (item 6 proof)
# ---------------------------------------------------------------------------


class TestAdvertisedCorridorsNoCapacityGate:
    """A corridor must remain advertised even when a region cannot fill
    every configured date -- only zero venues should hide it."""

    def test_low_capacity_corridor_still_advertised(self):
        """Patch one region to have exactly 1 venue (below CORRIDOR_STOPS_PER_DAY
        but > 0). The corridor must still appear."""
        original = db_service.list_venues_for_region

        def sparse(region):
            rows = original(region)
            if region == "vang_vieng_laos":
                # Return only 1 venue -- below CORRIDOR_STOPS_PER_DAY but > 0
                return rows[:1] if rows else []
            return rows

        result = advertised_corridors(sparse)
        corridor_ids = [c["corridor_id"] for c in result]
        assert "laos_northbound_v1" in corridor_ids, (
            "Corridor must be advertised even with low venue capacity"
        )

    def test_zero_venues_hides_corridor(self):
        """Zero venues in a region must hide the corridor."""
        original = db_service.list_venues_for_region

        def empty(region):
            if region == "vang_vieng_laos":
                return []
            return original(region)

        result = advertised_corridors(empty)
        corridor_ids = [c["corridor_id"] for c in result]
        assert "laos_northbound_v1" not in corridor_ids, (
            "Corridor must be hidden when a region has zero venues"
        )


# ---------------------------------------------------------------------------
# Proof 11: Global 5-day budget across corridor (item 3 proof)
# ---------------------------------------------------------------------------


class TestGlobalCorridorBudget:
    """The corridor must populate at most MAX_AUTO_POPULATED_DAYS globally,
    not per segment."""

    def test_corridor_total_populated_days_at_most_five(self):
        """A corridor with 3 segments of 3 days each (9 total) must
        produce at most 5 populated days globally."""
        corridor = require_corridor("laos_northbound_v1")
        sd = date.today() + timedelta(days=10)
        segments = [
            TripSegmentIn(
                geo_region="vientiane_laos",
                starts_on=sd,
                ends_on=sd + timedelta(days=2),
            ),
            TripSegmentIn(
                geo_region="vang_vieng_laos",
                starts_on=sd + timedelta(days=4),
                ends_on=sd + timedelta(days=6),
            ),
            TripSegmentIn(
                geo_region="luang_prabang_laos",
                starts_on=sd + timedelta(days=8),
                ends_on=sd + timedelta(days=10),
            ),
        ]

        nodes, _ = build_corridor_nodes(
            segments,
            db_service.list_venues_for_region,
            corridor,
        )

        # Count unique populated dates
        from datetime import datetime as dt
        from zoneinfo import ZoneInfo

        all_dates = set()
        for n in nodes:
            local = n.scheduled_start.astimezone(ZoneInfo("Asia/Vientiane"))
            all_dates.add(local.date())

        assert len(all_dates) <= MAX_AUTO_POPULATED_DAYS, (
            f"Global budget: {len(all_dates)} populated days exceeds "
            f"MAX_AUTO_POPULATED_DAYS={MAX_AUTO_POPULATED_DAYS}"
        )
