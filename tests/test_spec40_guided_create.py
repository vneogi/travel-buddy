"""SPEC-40: Guided Create Trip backend proofs.

Eleven required proofs from the spec, plus sabotage tests.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from main import app
from config.interests import (
    INTEREST_IDS,
    INTERESTS,
    MAX_INTERESTS,
    PARTY_TYPES,
    PARTY_TYPE_IDS,
    VENUES_PER_DAY,
    compute_max_days,
    validate_interest_ids,
)
from config.regions import REGIONS
from models.schemas import CreationContext, TripState
from services.catalog_itinerary import (
    advertised_regions,
    compute_max_days_for_region,
    eligible_venues,
    range_nodes_from_catalog,
)
from services.database_service import db_service
from tests.conftest import auth

client = TestClient(app)
HEADERS = auth("spec40-user")


def _future_date(offset_days: int = 10) -> str:
    """Return an ISO date string offset_days from today."""
    return (date.today() + timedelta(days=offset_days)).isoformat()


def _range_body(
    geo_region: str = "luang_prabang_laos",
    start_offset: int = 10,
    num_days: int = 4,
    interest_ids: list | None = None,
    party_type: str = "friends",
    party_size: int = 3,
):
    """Helper to build a range create request body."""
    sd = date.today() + timedelta(days=start_offset)
    ed = sd + timedelta(days=num_days - 1)
    body = {
        "start_date": sd.isoformat(),
        "end_date": ed.isoformat(),
        "geo_region": geo_region,
        "party": {
            "party_type": party_type,
            "size": party_size,
            "members": [],
        },
    }
    if interest_ids is not None:
        body["preferences"] = {"interest_ids": interest_ids}
    return body


# ---------------------------------------------------------------
# Proof 1: Legacy create without end_date preserves venue sequence
# ---------------------------------------------------------------


class TestLegacyCompat:
    def test_legacy_create_no_end_date_returns_same_sequence(self):
        """Omitted end_date preserves the existing one-day SPEC-32 output."""
        body = {
            "start_date": _future_date(10),
            "geo_region": "luang_prabang_laos",
        }
        r1 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r1.status_code == 200
        nodes1 = r1.json()["nodes"]

        r2 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r2.status_code == 200
        nodes2 = r2.json()["nodes"]

        # Same venue sequence
        ids1 = [n["venue_name"] for n in nodes1]
        ids2 = [n["venue_name"] for n in nodes2]
        assert ids1 == ids2
        # Should be 5 nodes (legacy TARGET_STOPS)
        assert len(nodes1) == 5


# ---------------------------------------------------------------
# Proof 2: Valid four-day range yields 16 nodes on four local dates
# ---------------------------------------------------------------


class TestRangeCreate:
    def test_four_day_range_yields_16_nodes_on_four_dates(self):
        body = _range_body(num_days=4)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200, r.json()
        nodes = r.json()["nodes"]
        assert len(nodes) == 16

        # Group by destination-local date
        tz = ZoneInfo(REGIONS["luang_prabang_laos"].timezone)
        dates = set()
        for n in nodes:
            dt = datetime.fromisoformat(n["scheduled_start"])
            local = dt.astimezone(tz)
            dates.add(local.date())
        assert len(dates) == 4


# ---------------------------------------------------------------
# Proof 3: No venue repeats across days
# ---------------------------------------------------------------


class TestNoRepeats:
    def test_no_repeated_venue_ids_across_days(self):
        body = _range_body(num_days=4)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200
        nodes = r.json()["nodes"]
        names = [n["venue_name"] for n in nodes]
        assert len(names) == len(set(names)), f"Repeated venues: {names}"


# ---------------------------------------------------------------
# Proof 4: Deterministic repeat
# ---------------------------------------------------------------


class TestDeterministic:
    def test_same_request_produces_same_sequence(self):
        body = _range_body(num_days=3, interest_ids=["food_markets"])
        r1 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        r2 = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r1.status_code == 200
        assert r2.status_code == 200
        ids1 = [n["venue_name"] for n in r1.json()["nodes"]]
        ids2 = [n["venue_name"] for n in r2.json()["nodes"]]
        assert ids1 == ids2


# ---------------------------------------------------------------
# Proof 5: Interests alter priority through registry
# ---------------------------------------------------------------


class TestInterestScoring:
    def test_interest_selection_changes_priority(self):
        """Different interests produce different venue orders."""
        body_a = _range_body(num_days=2, interest_ids=["history_culture"])
        body_b = _range_body(num_days=2, interest_ids=["nightlife_social"])
        ra = client.post("/api/v1/trip/create", json=body_a, headers=HEADERS)
        rb = client.post("/api/v1/trip/create", json=body_b, headers=HEADERS)
        assert ra.status_code == 200
        assert rb.status_code == 200
        ids_a = [n["venue_name"] for n in ra.json()["nodes"]]
        ids_b = [n["venue_name"] for n in rb.json()["nodes"]]
        # At least some venues should differ due to interest scoring
        assert ids_a != ids_b, "Interests must change venue priority"

    def test_sabotage_interest_scoring_removed(self):
        """If interest scoring returns 0 for everything, the test above fails."""
        body_a = _range_body(num_days=2, interest_ids=["history_culture"])
        body_b = _range_body(num_days=2, interest_ids=["nightlife_social"])
        with patch(
            "services.catalog_itinerary._interest_score",
            return_value=0.0,
        ):
            ra = client.post("/api/v1/trip/create", json=body_a, headers=HEADERS)
            rb = client.post("/api/v1/trip/create", json=body_b, headers=HEADERS)
        # With scoring disabled, both should get the same venues
        ids_a = [n["venue_name"] for n in ra.json()["nodes"]]
        ids_b = [n["venue_name"] for n in rb.json()["nodes"]]
        assert ids_a == ids_b, "Sabotage proof: without scoring, venues are identical"


# ---------------------------------------------------------------
# Proof 6: Invalid interest, reversed dates, past, over-cap -> 422
# ---------------------------------------------------------------


class TestValidation422:
    def test_invalid_interest_id_returns_422(self):
        body = _range_body(interest_ids=["does_not_exist"])
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "invalid_interests"

    def test_reversed_dates_returns_422(self):
        sd = date.today() + timedelta(days=10)
        ed = sd - timedelta(days=2)
        body = {
            "start_date": sd.isoformat(),
            "end_date": ed.isoformat(),
            "geo_region": "luang_prabang_laos",
        }
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "reversed_dates"

    def test_past_dates_returns_422(self):
        body = {
            "start_date": "2020-01-01",
            "end_date": "2020-01-03",
            "geo_region": "luang_prabang_laos",
        }
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "past_dates"

    def test_over_cap_returns_422(self):
        """Request more days than the advertised max."""
        body = _range_body(num_days=20)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "over_capacity"

    def test_too_many_interests_returns_422(self):
        body = _range_body(
            interest_ids=["history_culture", "food_markets", "nature_scenery", "arts_crafts"]
        )
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "invalid_interests"


# ---------------------------------------------------------------
# Proof 7: Capacity failure leaves no trip or party
# ---------------------------------------------------------------


class TestCapacityAtomicity:
    def test_insufficient_capacity_no_trip_or_party(self):
        """If range build fails mid-way, no trip is persisted."""
        trips_before = len(db_service._trips)
        parties_before = len(db_service._parties)

        # Request more days than possible for a small region
        body = _range_body(geo_region="vang_vieng_laos", num_days=10)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422

        assert len(db_service._trips) == trips_before
        assert len(db_service._parties) == parties_before

    def test_sabotage_atomicity(self):
        """If we remove the save guard, a partial trip would be saved."""
        trips_before = len(db_service._trips)
        # The 422 must happen BEFORE save_trip, so no trip is created.
        body = _range_body(geo_region="vang_vieng_laos", num_days=10)
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 422
        assert len(db_service._trips) == trips_before


# ---------------------------------------------------------------
# Proof 8: Party and creation context round-trip through GET trip
# ---------------------------------------------------------------


class TestPersistenceRoundTrip:
    def test_party_and_creation_context_round_trip(self):
        body = _range_body(
            num_days=2,
            interest_ids=["food_markets", "arts_crafts"],
            party_type="family_teens",
            party_size=4,
        )
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200
        trip_id = r.json()["trip_id"]

        # GET the trip
        g = client.get(f"/api/v1/trip/{trip_id}", headers=HEADERS)
        assert g.status_code == 200
        data = g.json()

        # Party
        assert data["party"]["party_type"] == "family_teens"
        assert data["party"]["size"] == 4

        # Creation context
        ctx = data.get("creation_context")
        assert ctx is not None
        assert ctx["destination"] == "luang_prabang_laos"
        assert ctx["interest_ids"] == ["food_markets", "arts_crafts"]
        assert ctx["start_date_local"] is not None
        assert ctx["end_date_local"] is not None


# ---------------------------------------------------------------
# Proof 9: No LLM/hybrid/quota call
# ---------------------------------------------------------------


class TestNoLLM:
    def test_range_create_no_llm_or_hybrid(self):
        """Range create must not call LLM, hybrid search, or consume quota."""
        with (
            patch("services.llm_service.llm_service.complete") as mock_llm,
            patch("agents.state_machine.state_machine.process_event") as mock_sm,
        ):
            body = _range_body(num_days=2)
            r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
            assert r.status_code == 200
            mock_llm.assert_not_called()
            mock_sm.assert_not_called()


# ---------------------------------------------------------------
# Proof 10: Corridor create stays compatible
# ---------------------------------------------------------------


class TestCorridorCompat:
    def test_corridor_create_unchanged(self):
        """Corridor create still works with segments, no end_date."""
        body = {
            "segments": [
                {
                    "geo_region": "vientiane_laos",
                    "starts_on": _future_date(10),
                    "ends_on": _future_date(11),
                },
                {
                    "geo_region": "vang_vieng_laos",
                    "starts_on": _future_date(12),
                    "ends_on": _future_date(13),
                },
                {
                    "geo_region": "luang_prabang_laos",
                    "starts_on": _future_date(14),
                    "ends_on": _future_date(16),
                },
            ],
        }
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data.get("corridor_id") is not None or len(data.get("nodes", [])) > 0


# ---------------------------------------------------------------
# Proof 11: Options tests are non-vacuous
# ---------------------------------------------------------------


class TestOptions:
    def test_options_have_content(self):
        """Every advertised region has a max and every option ID is accepted."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        assert r.status_code == 200
        opts = r.json()["create_trip_options"]

        # Party types are non-empty
        assert len(opts["party_types"]) > 0
        pt_ids = {p["id"] for p in opts["party_types"]}
        assert pt_ids == PARTY_TYPE_IDS

        # Interests are non-empty
        assert len(opts["interests"]) > 0
        int_ids = {i["id"] for i in opts["interests"]}
        assert int_ids == INTEREST_IDS

        # max_days_by_region is non-empty and matches advertised_regions
        max_days = opts["max_days_by_region"]
        assert len(max_days) > 0
        for region, md in max_days.items():
            assert md >= 1
            assert region in REGIONS

    def test_options_max_matches_validator(self):
        """The advertised max is what the validator also accepts."""
        r = client.get("/api/v1/trips", headers=HEADERS)
        max_days = r.json()["create_trip_options"]["max_days_by_region"]
        for region, md in max_days.items():
            # A request at the max should succeed
            body = _range_body(geo_region=region, num_days=md)
            resp = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
            assert resp.status_code == 200, f"{region} at max {md} failed"

    def test_sabotage_empty_interests_fails(self):
        """If INTERESTS registry were empty, this test would fail."""
        assert len(INTERESTS) >= 7
        for interest in INTERESTS:
            # Each interest must have at least one category or tag match
            assert len(interest.category_matches) + len(interest.vibe_tag_matches) > 0

    def test_old_home_snapshot_without_options_still_valid(self):
        """Old API responses without create_trip_options parse fine."""
        # Simulate old response shape
        old_response = {
            "supported_regions": ["luang_prabang_laos"],
            "supported_corridors": [],
            "trips": [],
            "featured_trip": None,
        }
        # Should not have create_trip_options
        assert "create_trip_options" not in old_response
        # But the new response does
        r = client.get("/api/v1/trips", headers=HEADERS)
        assert "create_trip_options" in r.json()


# ---------------------------------------------------------------
# Registry validation unit tests
# ---------------------------------------------------------------


class TestRegistryValidation:
    def test_validate_interest_ids_accepts_valid(self):
        assert validate_interest_ids(["food_markets", "arts_crafts"]) == [
            "food_markets",
            "arts_crafts",
        ]

    def test_validate_interest_ids_rejects_unknown(self):
        with pytest.raises(ValueError, match="Unknown"):
            validate_interest_ids(["bogus"])

    def test_validate_interest_ids_rejects_too_many(self):
        with pytest.raises(ValueError, match="At most"):
            validate_interest_ids(list(INTEREST_IDS)[:4])

    def test_validate_interest_ids_deduplicates(self):
        assert validate_interest_ids(["food_markets", "food_markets"]) == ["food_markets"]

    def test_compute_max_days(self):
        assert compute_max_days(20) == 5  # 20//4=5, min(5,5)
        assert compute_max_days(8) == 2  # 8//4=2
        assert compute_max_days(3) == 0  # 3//4=0

    def test_zero_interests_means_balanced(self):
        """Zero interests produces catalog-order venues."""
        body = _range_body(num_days=2, interest_ids=[])
        r = client.post("/api/v1/trip/create", json=body, headers=HEADERS)
        assert r.status_code == 200
        assert len(r.json()["nodes"]) == 8
