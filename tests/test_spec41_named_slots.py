"""SPEC-41 Slice 3: Named day slots and travel-day occupancy.

Proofs required by the brief:

  1. A feasible mixed-window catalog fills morning, lunch,
     afternoon/evening, dinner rather than four morning stops.
  2. A whole-day excursion occupies morning + afternoon and leaves
     dinner as the only remaining generated recommendation.
  3. An early-evening arrival packs dinner only.
  4. A mid-afternoon arrival plus hotel check-in packs at most
     afternoon/evening plus dinner.
  5. Insufficient remaining slots leave open time, no filler.
  6. Existing SPEC-41 hours/reachability tests pass (run via pytest -q).

All slot-name assertions operate on TripNode.slot_name returned by
pack_day.  Flutter rendering is UNVERIFIED without the Flutter SDK.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from services.catalog_itinerary import pack_day
from services.day_slots import (
    SLOT_ORDER,
    WHOLE_DAY_VIBE_TAGS,
    assign_slot,
    compute_remaining_slots,
    has_matching_slot,
    is_food_venue,
    is_whole_day_excursion,
)

ICT = ZoneInfo("Asia/Vientiane")  # UTC+7
GEO = "luang_prabang_laos"

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

_ALL_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _hours(start: str, end: str) -> dict:
    return {d: [[start, end]] for d in _ALL_DAYS}


def _venue(
    name: str,
    category: str = "temple",
    lat: float = 19.89,
    lng: float = 102.13,
    dwell: int = 60,
    hours_start: str = "09:00",
    hours_end: str = "21:00",
    vibe_tags: list | None = None,
) -> dict:
    from services.catalog_itinerary import flatten_opening_hours

    structured = _hours(hours_start, hours_end)
    return {
        "name": name,
        "venue_id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)),
        "description": "",
        "micro_location": "",
        "lat": lat,
        "lng": lng,
        "vibe_tags": list(vibe_tags or []),
        "audience": [],
        "category": category,
        "opening_hours": flatten_opening_hours(structured),
        "opening_hours_structured": structured,
        "typical_dwell_minutes": dwell,
        "geo_region": GEO,
    }


def _day_start(year: int, month: int, day: int, hour: int = 0) -> datetime:
    """UTC midnight (or given hour) on a Laos calendar date."""
    return datetime(year, month, day, hour, 0, 0, tzinfo=ICT).astimezone(timezone.utc)


# -----------------------------------------------------------------------
# Unit tests: day_slots helpers
# -----------------------------------------------------------------------


class TestSlotHelpers:
    def test_slot_order_has_four_entries(self):
        assert list(SLOT_ORDER) == [
            "morning_tour",
            "lunch",
            "afternoon_evening_tour",
            "dinner",
        ]

    def test_is_food_venue_restaurant(self):
        assert is_food_venue({"category": "restaurant"})
        assert is_food_venue({"category": "cafe"})
        assert is_food_venue({"category": "street_food"})

    def test_is_food_venue_activity(self):
        assert not is_food_venue({"category": "temple"})
        assert not is_food_venue({"category": "experience"})
        assert not is_food_venue({})

    def test_is_whole_day_excursion_tag(self):
        for tag in WHOLE_DAY_VIBE_TAGS:
            assert is_whole_day_excursion({"vibe_tags": [tag]})

    def test_is_whole_day_excursion_false_for_normal_venue(self):
        assert not is_whole_day_excursion({"category": "temple", "vibe_tags": ["historic"]})

    def test_assign_slot_activity_consumes_morning_first(self):
        venue = {"category": "temple", "vibe_tags": []}
        slot, remaining = assign_slot(venue, list(SLOT_ORDER))
        assert slot == "morning_tour"
        assert remaining == ["lunch", "afternoon_evening_tour", "dinner"]

    def test_assign_slot_food_consumes_lunch_first(self):
        venue = {"category": "restaurant", "vibe_tags": []}
        slot, remaining = assign_slot(venue, list(SLOT_ORDER))
        assert slot == "lunch"
        assert remaining == ["morning_tour", "afternoon_evening_tour", "dinner"]

    def test_assign_slot_food_uses_dinner_when_lunch_gone(self):
        venue = {"category": "restaurant", "vibe_tags": []}
        slots = ["morning_tour", "afternoon_evening_tour", "dinner"]
        slot, remaining = assign_slot(venue, slots)
        assert slot == "dinner"
        assert remaining == ["morning_tour", "afternoon_evening_tour"]

    def test_assign_slot_whole_day_consumes_three(self):
        tag = next(iter(WHOLE_DAY_VIBE_TAGS))
        venue = {"category": "experience", "vibe_tags": [tag]}
        slot, remaining = assign_slot(venue, list(SLOT_ORDER))
        assert slot == "morning_tour"
        assert remaining == ["dinner"]

    def test_assign_slot_raises_when_no_activity_slot(self):
        venue = {"category": "temple", "vibe_tags": []}
        with pytest.raises(ValueError, match="No activity slot"):
            assign_slot(venue, ["lunch", "dinner"])

    def test_assign_slot_raises_when_no_food_slot(self):
        venue = {"category": "restaurant", "vibe_tags": []}
        with pytest.raises(ValueError, match="No food slot"):
            assign_slot(venue, ["morning_tour", "afternoon_evening_tour"])

    def test_has_matching_slot_activity(self):
        assert has_matching_slot({"category": "temple", "vibe_tags": []}, ["morning_tour"])
        assert not has_matching_slot({"category": "temple", "vibe_tags": []}, ["lunch", "dinner"])

    def test_has_matching_slot_food(self):
        assert has_matching_slot({"category": "restaurant", "vibe_tags": []}, ["dinner"])
        assert not has_matching_slot({"category": "restaurant", "vibe_tags": []}, ["morning_tour"])


# -----------------------------------------------------------------------
# Unit tests: compute_remaining_slots
# -----------------------------------------------------------------------


class TestComputeRemainingSlots:
    def test_early_evening_arrival_dinner_only(self):
        """SPEC-41: landing or arriving early evening -> dinner only."""
        assert compute_remaining_slots(17, "flight", has_hotel=False) == ["dinner"]
        assert compute_remaining_slots(19, "train", has_hotel=True) == ["dinner"]
        assert compute_remaining_slots(22, None, has_hotel=False) == ["dinner"]

    def test_mid_afternoon_arrival_evening_plus_dinner(self):
        """SPEC-41: 15:00 arrival + hotel check-in -> at most evening plus dinner."""
        result = compute_remaining_slots(15, "train", has_hotel=True)
        assert result == ["afternoon_evening_tour", "dinner"]

    def test_mid_afternoon_no_hotel_same_result(self):
        result = compute_remaining_slots(14, "train", has_hotel=False)
        assert result == ["afternoon_evening_tour", "dinner"]

    def test_morning_departure_no_morning_tour(self):
        """SPEC-41: morning departure flight -> no morning tour."""
        result = compute_remaining_slots(7, "flight", has_hotel=False)
        assert result == ["lunch", "afternoon_evening_tour", "dinner"]
        assert "morning_tour" not in result

    def test_morning_train_departure_no_morning_tour(self):
        result = compute_remaining_slots(8, "train", has_hotel=True)
        assert result == ["lunch", "afternoon_evening_tour", "dinner"]

    def test_full_day_returns_all_slots(self):
        result = compute_remaining_slots(9, None, has_hotel=False)
        assert result == list(SLOT_ORDER)

    def test_noon_departure_non_travel_full_day(self):
        # Departure at 12:00 is not < 12, so full day.
        result = compute_remaining_slots(12, "flight", has_hotel=False)
        assert result == list(SLOT_ORDER)

    def test_hotel_checkout_morning_only(self):
        """Hotel booking before noon: checkout-day, morning slot only."""
        result = compute_remaining_slots(10, "hotel", has_hotel=True)
        assert result == ["morning_tour"]
        # Very early checkout also morning-only.
        result2 = compute_remaining_slots(6, "hotel", has_hotel=True)
        assert result2 == ["morning_tour"]


# -----------------------------------------------------------------------
# Proof 1: mixed-window catalog fills all four named slots
# -----------------------------------------------------------------------


class TestMixedWindowFillsAllSlots:
    """SPEC-41 proof: morning, lunch, afternoon, dinner -- not four morning stops."""

    def test_four_slots_assigned_to_correct_types(self):
        # Two activity venues (distinct coords to avoid same-location dedup),
        # two food venues.  All open 09:00-22:00.
        pool = [
            _venue("Wat Xieng Thong", category="temple", lat=19.89, lng=102.13),
            _venue("Kuang Si Falls", category="nature", lat=19.74, lng=101.98),
            _venue("Tamarind Restaurant", category="restaurant", lat=19.89, lng=102.13),
            _venue("Night Market Food", category="street_food", lat=19.88, lng=102.14),
        ]
        day_start = _day_start(2026, 10, 3)  # Friday
        # Pass remaining_slots=SLOT_ORDER so slot-type filtering applies.
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=list(SLOT_ORDER),
        )
        slot_names = [n.slot_name for n in nodes]
        assert "morning_tour" in slot_names, "expected a morning slot"
        assert "afternoon_evening_tour" in slot_names, "expected an afternoon slot"
        # At least one food slot filled
        assert "lunch" in slot_names or "dinner" in slot_names, "expected a food slot"
        # No duplicate slots
        assert len(slot_names) == len(set(slot_names)), "duplicate slot names"

    def test_scheduled_starts_follow_named_slot_order(self):
        """Flexible in-city day must schedule in morning, lunch, afternoon, dinner order."""
        pool = [
            _venue(
                "Temple A",
                category="temple",
                lat=19.89,
                lng=102.13,
                hours_start="09:00",
                hours_end="17:00",
            ),
            _venue(
                "Cafe B",
                category="cafe",
                lat=19.88,
                lng=102.12,
                hours_start="09:00",
                hours_end="17:00",
            ),
            _venue(
                "Night Market",
                category="market",
                lat=19.90,
                lng=102.14,
                hours_start="17:00",
                hours_end="22:00",
            ),
            _venue(
                "Dinner C",
                category="restaurant",
                lat=19.87,
                lng=102.11,
                hours_start="17:00",
                hours_end="22:00",
            ),
        ]
        day_start = _day_start(2026, 10, 3)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=list(SLOT_ORDER),
        )
        assert [n.slot_name for n in nodes] == [
            "morning_tour",
            "lunch",
            "afternoon_evening_tour",
            "dinner",
        ]
        starts = [n.scheduled_start for n in nodes]
        assert starts == sorted(starts)

    def test_slot_names_match_category_type(self):
        """Activity venues must not receive food slots and vice versa."""
        pool = [
            _venue("Temple A", category="temple", lat=19.89, lng=102.13),
            _venue("Market B", category="market", lat=19.90, lng=102.14),
            _venue("Restaurant C", category="restaurant", lat=19.88, lng=102.12),
            _venue("Cafe D", category="cafe", lat=19.87, lng=102.13),
        ]
        day_start = _day_start(2026, 10, 3)
        # Constrained mode guarantees slot-type correctness.
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=list(SLOT_ORDER),
        )
        food_slots = {"lunch", "dinner"}
        activity_slots = {"morning_tour", "afternoon_evening_tour"}
        for node in nodes:
            # Look up the venue dict to get the category
            venue = next(v for v in pool if v["name"] == node.venue_name)
            if is_food_venue(venue):
                assert node.slot_name in food_slots, (
                    f"{node.venue_name} (food) got slot {node.slot_name}"
                )
            else:
                assert node.slot_name in activity_slots, (
                    f"{node.venue_name} (activity) got slot {node.slot_name}"
                )


# -----------------------------------------------------------------------
# Proof 2: whole-day excursion occupies morning+afternoon, leaves dinner
# -----------------------------------------------------------------------


class TestWholeDayExcursion:
    def test_whole_day_leaves_only_dinner(self):
        """SPEC-41: whole-day excursion occupies morning, lunch, afternoon.
        Only dinner may be generated afterward.
        """
        any_whole_day_tag = next(iter(WHOLE_DAY_VIBE_TAGS))
        pool = [
            _venue(
                "Pak Ou Cave Excursion",
                category="experience",
                lat=19.89,
                lng=102.13,
                vibe_tags=[any_whole_day_tag],
                hours_start="08:00",
                hours_end="18:00",
                dwell=480,
            ),
            _venue(
                "Dinner Restaurant",
                category="restaurant",
                lat=19.88,
                lng=102.12,
                hours_start="17:00",
                hours_end="22:00",
            ),
            _venue(
                "Extra Temple",
                category="temple",
                lat=19.90,
                lng=102.14,
                hours_start="09:00",
                hours_end="17:00",
            ),
        ]
        day_start = _day_start(2026, 10, 3)
        # Constrained mode: whole-day excursion consumes all three non-dinner slots.
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=list(SLOT_ORDER),
        )
        slot_names = [n.slot_name for n in nodes]
        assert "morning_tour" in slot_names, "excursion must occupy morning_tour"
        assert "afternoon_evening_tour" not in slot_names, (
            "afternoon slot consumed by excursion; no second activity"
        )
        assert "lunch" not in slot_names, "lunch consumed by excursion"
        assert "dinner" in slot_names, "dinner must still be generated"
        # Extra Temple must not appear (all activity slots consumed by excursion)
        node_names = [n.venue_name for n in nodes]
        assert "Extra Temple" not in node_names, "no extra activity after whole-day excursion"


# -----------------------------------------------------------------------
# Proof 3: early-evening arrival packs dinner only
# -----------------------------------------------------------------------


class TestEarlyEveningArrival:
    def test_dinner_only(self):
        """SPEC-41: early-evening arrival -> dinner only."""
        remaining = compute_remaining_slots(18, "flight", has_hotel=True)
        assert remaining == ["dinner"]

        pool = [
            _venue("Evening Temple", category="temple", lat=19.89, lng=102.13),
            _venue("Dinner Spot", category="restaurant", lat=19.88, lng=102.12),
        ]
        day_start = _day_start(2026, 10, 2)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=remaining,
        )
        assert len(nodes) == 1, f"expected 1 node (dinner only), got {len(nodes)}"
        assert nodes[0].slot_name == "dinner"
        assert nodes[0].venue_name == "Dinner Spot"

    def test_no_activity_generated_on_late_arrival(self):
        """Activity venue must not be packed when only dinner slot remains."""
        remaining = compute_remaining_slots(19, None, has_hotel=False)
        pool = [
            _venue("Night Temple", category="temple", lat=19.89, lng=102.13),
        ]
        day_start = _day_start(2026, 10, 2)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=remaining,
        )
        assert nodes == [], "activity venue must not be packed when only dinner slot remains"


# -----------------------------------------------------------------------
# Proof 3b: thin-catalog proofs (strict slot typing)
# -----------------------------------------------------------------------


class TestThinCatalogStrictTyping:
    """Missing food produces no lunch/dinner rather than relabeling an activity."""

    def test_activity_only_pool_skips_food_slots(self):
        """A pool with only activity venues produces morning + afternoon, no lunch/dinner."""
        pool = [
            _venue("Temple A", category="temple", lat=19.89, lng=102.13),
            _venue("Museum B", category="museum", lat=19.88, lng=102.12),
            _venue("Market C", category="market", lat=19.90, lng=102.14),
        ]
        day_start = _day_start(2026, 10, 2)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
        )
        slot_names = {n.slot_name for n in nodes}
        assert "lunch" not in slot_names, "activity must not fill lunch slot"
        assert "dinner" not in slot_names, "activity must not fill dinner slot"
        assert len(nodes) == 2, "only morning_tour + afternoon_evening_tour"

    def test_food_only_pool_skips_activity_slots(self):
        """A pool with only food venues produces lunch + dinner, no morning/afternoon."""
        pool = [
            _venue("Cafe A", category="cafe", lat=19.89, lng=102.13),
            _venue(
                "Restaurant B",
                category="restaurant",
                lat=19.88,
                lng=102.12,
                hours_start="09:00",
                hours_end="22:00",
            ),
        ]
        day_start = _day_start(2026, 10, 2)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
        )
        slot_names = {n.slot_name for n in nodes}
        assert "morning_tour" not in slot_names, "food must not fill morning_tour slot"
        assert "afternoon_evening_tour" not in slot_names, "food must not fill afternoon slot"
        assert len(nodes) == 2, "only lunch + dinner"

    def test_whole_day_excursion_never_in_dinner(self):
        """A whole-day excursion only fills morning; never dinner or afternoon alone."""
        pool = [
            _venue(
                "Island Trip",
                category="experience",
                lat=19.89,
                lng=102.13,
                vibe_tags=["island_hopping"],
            ),
        ]
        day_start = _day_start(2026, 10, 2)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=["dinner"],
        )
        assert nodes == [], "whole-day excursion must not fill dinner slot"


# -----------------------------------------------------------------------
# Proof 4: mid-afternoon arrival + hotel -> at most evening + dinner
# -----------------------------------------------------------------------


class TestMidAfternoonArrival:
    def test_at_most_two_nodes_evening_and_dinner(self):
        """SPEC-41: 15:00 train + hotel check-in -> afternoon_evening_tour, dinner."""
        remaining = compute_remaining_slots(15, "train", has_hotel=True)
        assert remaining == ["afternoon_evening_tour", "dinner"]

        pool = [
            _venue("Morning Temple", category="temple", lat=19.89, lng=102.13),
            _venue("Afternoon Walk", category="walking_area", lat=19.90, lng=102.14),
            _venue("Dinner Restaurant", category="restaurant", lat=19.88, lng=102.12),
        ]
        day_start = _day_start(2026, 10, 4)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=remaining,
        )
        slot_names = [n.slot_name for n in nodes]
        assert len(nodes) <= 2, f"expected at most 2 nodes, got {len(nodes)}"
        assert "morning_tour" not in slot_names, "no morning tour after mid-afternoon arrival"
        assert "lunch" not in slot_names, "no lunch after mid-afternoon arrival"

    def test_morning_temple_not_packed(self):
        """morning_tour slot not present -> morning venue is rejected."""
        remaining = ["afternoon_evening_tour", "dinner"]
        pool = [
            _venue("Morning Temple", category="temple", lat=19.89, lng=102.13),
        ]
        day_start = _day_start(2026, 10, 4)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=remaining,
        )
        # Only afternoon_evening_tour or dinner are valid.  A temple is an
        # activity -> afternoon_evening_tour is available, so it may be packed.
        # But morning_tour must not appear.
        for node in nodes:
            assert node.slot_name != "morning_tour"


# -----------------------------------------------------------------------
# Proof 5: empty remaining slots -> no filler
# -----------------------------------------------------------------------


class TestInsufficientRemainingSlots:
    def test_empty_remaining_returns_no_nodes(self):
        """SPEC-41: insufficient remaining slots -> open time, no filler."""
        pool = [
            _venue("Temple A", category="temple", lat=19.89, lng=102.13),
            _venue("Restaurant B", category="restaurant", lat=19.88, lng=102.12),
        ]
        day_start = _day_start(2026, 10, 5)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=[],
        )
        assert nodes == [], "empty remaining_slots must produce no nodes"

    def test_single_slot_produces_at_most_one_node(self):
        pool = [
            _venue("Temple A", category="temple", lat=19.89, lng=102.13),
            _venue("Temple B", category="temple", lat=19.90, lng=102.14),
        ]
        day_start = _day_start(2026, 10, 5)
        nodes, _ = pack_day(
            candidates=pool,
            target_count=4,
            day_start_utc=day_start,
            geo_region=GEO,
            used_ids=set(),
            remaining_slots=["morning_tour"],
        )
        assert len(nodes) == 1
        assert nodes[0].slot_name == "morning_tour"


# -----------------------------------------------------------------------
# Proof 6: slot_name is None for locked booking nodes
# -----------------------------------------------------------------------


class TestLockedBookingSlotName:
    def test_locked_booking_has_no_slot_name(self):
        from datetime import timedelta
        from models.schemas import TripNode

        node = TripNode(
            venue_name="Laos Airways LF321",
            scheduled_start=datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),
            duration_minutes=90,
            is_locked=True,
            node_kind="booking",
            booking_type="flight",
        )
        assert node.slot_name is None, "locked bookings must not carry a slot name"


# -----------------------------------------------------------------------
# Proof 7: Proximity-to-centroid tie-breaking
# -----------------------------------------------------------------------


class TestProximityRanking:
    """Prove the centroid-based tie-breaker changes venue selection."""

    # 09:00 ICT Sep 14 = 02:00 UTC
    _DAY_START = datetime(2026, 9, 14, 2, 0, tzinfo=timezone.utc)

    def _pack(self, candidates, interest_ids=()):
        nodes, _ = pack_day(
            candidates=candidates,
            target_count=4,
            day_start_utc=self._DAY_START,
            geo_region=GEO,
            used_ids=set(),
            interest_ids=interest_ids,
        )
        return nodes

    def test_cluster_venue_wins_over_outlier_on_tie(self):
        """When interest scores tie (both 0), the venue closer to the
        pool centroid wins the first activity slot.

        Two temples compete for activity slots: one at the cluster centre,
        one offset by ~0.07 deg.  The centroid is pulled toward the cluster
        (cafe + restaurant also at 19.89).  Close Temple sorts first.
        """
        close = _venue("Close Temple", category="temple")
        outlier = _venue("Outlier Temple", category="temple", lat=19.95, lng=102.20)
        cafe = _venue("Cafe A", category="cafe")
        food = _venue("Restaurant B", category="restaurant")

        nodes = self._pack([outlier, close, cafe, food])
        names = [n.venue_name for n in nodes]
        assert "Close Temple" in names
        assert "Outlier Temple" in names
        assert names.index("Close Temple") < names.index("Outlier Temple"), (
            "cluster venue must rank before outlier when interest scores tie"
        )

    def test_higher_interest_outranks_proximity(self):
        """A high-interest venue beats a closer-to-centroid venue even when
        the high-interest venue is farther from the centroid.

        history_culture matches temple but not viewpoint.  Without the
        interest, the close viewpoint wins the first activity slot;
        with it, the moderate-distance temple wins instead.
        """
        from config.interests import get_interest

        interest_id = "history_culture"
        interest_def = get_interest(interest_id)
        assert "temple" in interest_def.category_matches, (
            "test assumes 'history_culture' matches 'temple'"
        )

        close_view = _venue("Close Viewpoint", category="viewpoint")
        moderate_temple = _venue("Moderate Temple", category="temple", lat=19.94, lng=102.18)
        cafe = _venue("Cafe One", category="cafe")
        food = _venue("Cafe Two", category="restaurant")

        with_interest = self._pack(
            [close_view, moderate_temple, cafe, food],
            interest_ids=[interest_id],
        )
        without_interest = self._pack([close_view, moderate_temple, cafe, food])

        names_with = [n.venue_name for n in with_interest]
        names_without = [n.venue_name for n in without_interest]

        # With interest: temple (score 1) should be selected first.
        assert names_with[0] == "Moderate Temple", (
            "high-interest temple must be first with history_culture interest"
        )
        # Without interest: viewpoint (closer) should be first.
        assert names_without[0] == "Close Viewpoint", (
            "closer viewpoint must be first without interest"
        )

    def test_ordering_is_deterministic(self):
        """Same input always produces the same output order.

        Run pack_day twice with identical inputs and confirm the node
        order is identical.
        """
        pool = [
            _venue("Alpha Temple", category="temple"),
            _venue("Beta Cafe", category="cafe"),
            _venue("Gamma Market", category="market"),
            _venue("Delta View", category="viewpoint"),
        ]
        nodes_a = self._pack(pool)
        nodes_b = self._pack(pool)
        names_a = [n.venue_name for n in nodes_a]
        names_b = [n.venue_name for n in nodes_b]
        assert names_a == names_b, "ordering must be deterministic across identical runs"
