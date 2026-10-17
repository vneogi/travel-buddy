"""SPEC-46 Phase A: What Now deterministic handler tests."""

from datetime import datetime, timedelta, timezone

import pytest

from models.schemas import AskResponseEnvelope
from services.ask_service import (
    AskIntent,
    AskPath,
    TrustTier,
    WhatNowRequest,
    handle_what_now,
)

OPEN_ALL_DAY = {d: [["08:00", "22:00"]] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
CLOSED_ALL_DAY = {d: [] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}


class FakeDb:
    def __init__(self, rows: dict[str, list[dict]]):
        self._rows = rows
        self.calls: list[str] = []

    def list_venues_for_region(self, geo_region: str):
        self.calls.append(geo_region)
        return [dict(r) for r in self._rows.get(geo_region, [])]


@pytest.fixture
def now_utc():
    return datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def ctx_node(now_utc):
    return {
        "node_id": "n1",
        "venue_name": "Context Temple",
        "venue_id": "ctx-1",
        "scheduled_start": (now_utc - timedelta(minutes=30)).isoformat(),
        "duration_minutes": 60,
        "geo_region": "vientiane_laos",
        "micro_location": "nam_phou_fountain",
        "lat": 17.96345,
        "lng": 102.61112,
        "vibe_tags": ["quiet", "culture"],
        "is_locked": False,
        "node_kind": "activity",
    }


def _v(
    vid,
    name,
    *,
    geo="vientiane_laos",
    cat="temple",
    ml="nam_phou_fountain",
    lat=17.9640,
    lng=102.6120,
    dwell=45,
    hours=None,
    vibes=None,
    indoor="mixed",
    aircon=False,
):
    return {
        "venue_id": vid,
        "name": name,
        "geo_region": geo,
        "category": cat,
        "micro_location": ml,
        "lat": lat,
        "lng": lng,
        "typical_dwell_minutes": dwell,
        "opening_hours": OPEN_ALL_DAY if hours is None else hours,
        "vibe_tags": vibes or [],
        "indoor_outdoor": indoor,
        "has_aircon": aircon,
    }


class TestRegionIsolation:
    def test_vientiane_never_returns_other_regions(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [_v("vt-1", "Wat Si Saket")],
                "dubai_uae": [_v("dxb", "Dubai Mall", geo="dubai_uae")],
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="culture"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert db.calls == ["vientiane_laos"]
        names = [c["name"] for c in resp.what_now["candidates"]]
        assert names == ["Wat Si Saket"]


class TestExclusions:
    def test_infrastructure_itinerary_context_excluded(self, now_utc, ctx_node):
        itin = {
            **ctx_node,
            "node_id": "n2",
            "venue_name": "Planned Cafe",
            "venue_id": "it-1",
            "scheduled_start": (now_utc + timedelta(hours=2)).isoformat(),
        }
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("ctx-1", "Context Temple"),
                    _v("it-1", "Planned Cafe", cat="cafe"),
                    _v("ph-1", "Pharmacy", cat="pharmacy"),
                    _v("ok-1", "Saffron", cat="cafe"),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="anything"),
            [ctx_node, itin],
            now_utc,
            "vientiane_laos",
            db,
        )
        ids = [c["venue_id"] for c in resp.what_now["candidates"]]
        assert ids == ["ok-1"]


class TestAvailableWindow:
    def test_90min_rejects_dwell_plus_walking_over_90(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("near", "Near", dwell=45),
                    _v(
                        "far",
                        "Far",
                        cat="museum",
                        dwell=65,
                        lat=17.98545,
                        lng=102.61112,
                    ),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, walking="longer"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        ids = [c["venue_id"] for c in resp.what_now["candidates"]]
        assert "near" in ids
        assert "far" not in ids


class TestHoursExclusion:
    def test_known_closed_excluded(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("open", "Open", cat="museum"),
                    _v("shut", "Shut", hours=CLOSED_ALL_DAY),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        ids = [c["venue_id"] for c in resp.what_now["candidates"]]
        assert ids == ["open"]


class TestBookingBoundary:
    def test_next_locked_booking_reachable(self, now_utc, ctx_node):
        booking = {
            "node_id": "b1",
            "venue_name": "Train",
            "venue_id": "bk-1",
            "scheduled_start": (now_utc + timedelta(minutes=70)).isoformat(),
            "duration_minutes": 30,
            "geo_region": "vientiane_laos",
            "is_locked": True,
            "node_kind": "booking",
        }
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("s", "Quick", cat="cafe", dwell=30),
                    _v("l", "Long", cat="museum", dwell=90),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node, booking],
            now_utc,
            "vientiane_laos",
            db,
        )
        ids = [c["venue_id"] for c in resp.what_now["candidates"]]
        assert "s" in ids
        assert "l" not in ids


class TestRegionAnchor:
    def test_no_distance_or_walk_claim(self, now_utc):
        db = FakeDb({"vientiane_laos": [_v("vt", "Wat Si Saket")]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="culture"),
            [],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.what_now["location_source"] == "region_anchor"
        c = resp.what_now["candidates"][0]
        assert "short_walk_from_context" not in c["reason_codes"]
        assert "same_neighbourhood" not in c["reason_codes"]


class TestInvalidContext:
    def test_foreign_node_refuses(self, now_utc, ctx_node):
        db = FakeDb({"vientiane_laos": [_v("vt", "Wat")]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, context_node_id="foreign"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.path == AskPath.RETRIEVAL_MISS
        assert resp.tier == TrustTier.REFUSE
        assert resp.what_now is None


class TestMissingCoordinates:
    def test_no_short_walk_without_coords(self, now_utc, ctx_node):
        db = FakeDb(
            {"vientiane_laos": [_v("unk", "No Coords", cat="museum", lat=None, lng=None, dwell=45)]}
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        c = resp.what_now["candidates"][0]
        assert "short_walk_from_context" not in c["reason_codes"]
        assert "walking_time" in c["unknown_fields"]


class TestReasonPredicates:
    def test_every_emitted_code_has_predicate(self, now_utc, ctx_node):
        db = FakeDb({"vientiane_laos": [_v("vt", "Wat Si Saket", vibes=["quiet"])]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90, intent="culture"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        allowed = {
            "fits_available_window",
            "open_for_planned_time",
            "keeps_next_booking_reachable",
            "matches_requested_type",
            "matches_trip_interest",
            "same_neighbourhood",
            "short_walk_from_context",
            "lower_typical_dwell",
            "indoor_option",
        }
        for c in resp.what_now["candidates"]:
            for code in c["reason_codes"]:
                assert code in allowed, f"Unknown reason code: {code}"


class TestRetrievalMiss:
    def test_no_feasible_returns_miss(self, now_utc, ctx_node):
        db = FakeDb(
            {
                "vientiane_laos": [
                    _v("x", "Closed", hours=CLOSED_ALL_DAY),
                    _v("y", "Huge", dwell=180, cat="museum"),
                ]
            }
        )
        resp = handle_what_now(
            WhatNowRequest(available_minutes=45, walking="short"),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.path == AskPath.RETRIEVAL_MISS
        assert resp.tier == TrustTier.REFUSE


class TestNoLLM:
    def test_zero_llm_calls(self, now_utc, ctx_node):
        db = FakeDb({"vientiane_laos": [_v("vt", "Wat")]})
        resp = handle_what_now(
            WhatNowRequest(available_minutes=90),
            [ctx_node],
            now_utc,
            "vientiane_laos",
            db,
        )
        assert resp.path == AskPath.GROUNDED_DETERMINISTIC


class TestEnvelopeContract:
    def test_pydantic_envelope_accepts_what_now(self):
        env = AskResponseEnvelope(
            answer="Found 1",
            tier="hedge",
            path="grounded_deterministic",
            intent="what_now",
            source_ids=["vt-1"],
            source_class="curated_catalog",
            what_now={
                "location_source": "trip_position",
                "context_label": "Using your trip position",
                "candidates": [
                    {
                        "candidate_id": "what_now:vt-1",
                        "venue_id": "vt-1",
                        "name": "Wat",
                        "reason_codes": ["fits_available_window"],
                        "unknown_fields": ["price"],
                    }
                ],
            },
        )
        assert env.what_now.location_source == "trip_position"


class TestValidation:
    def test_invalid_duration_rejects(self):
        with pytest.raises(ValueError):
            WhatNowRequest(available_minutes=30)

    def test_invalid_energy_rejects(self):
        with pytest.raises(ValueError):
            WhatNowRequest(available_minutes=90, energy="extreme")
