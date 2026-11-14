"""SPEC-41 follow-up: a bar fills only the afternoon/evening slot.

Owner field test 2026-11-14: a Nungwi day put "Cholo's Beach by Bento"
(category bar) in the morning slot. The rule lives in services/day_slots.py,
so pack_day, swap candidates and swap confirm all follow it. Helpers are
copied from tests/test_spec41_window_packing.py (not imported); the venue
row helper takes geo_region and coordinates so Nungwi rows stay in Nungwi.
No network, no database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

import pytest

import services.day_slots as day_slots
from services.catalog_itinerary import is_swap_eligible_venue, pack_day
from services.day_slots import (
    SLOT_ORDER,
    assign_slot,
    has_matching_slot,
    is_afternoon_only_venue,
    venue_fits_slot,
)

EAT = ZoneInfo("Africa/Dar_es_Salaam")
GEO = "nungwi_tanzania"
NUNGWI = (-5.72720, 39.29920)

_ALL_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _make_hours(weekday_windows: Dict[str, list]) -> Dict[str, Any]:
    return {d: weekday_windows.get(d, [["09:00", "17:00"]]) for d in _ALL_DAYS}


def _make_venue_row(
    name,
    structured=None,
    category="temple",
    dwell=60,
    lat=NUNGWI[0],
    lng=NUNGWI[1],
    venue_id=None,
    vibe_tags=None,
    geo_region=GEO,
):
    from services.catalog_itinerary import flatten_opening_hours

    flat = flatten_opening_hours(structured) or "09:00-17:00"
    return {
        "name": name,
        "venue_id": venue_id or str(uuid.uuid5(uuid.NAMESPACE_URL, name)),
        "description": "",
        "micro_location": "",
        "lat": lat,
        "lng": lng,
        "vibe_tags": list(vibe_tags or []),
        "audience": [],
        "category": category,
        "opening_hours": flat,
        "opening_hours_structured": structured,
        "geo_region": geo_region,
        "typical_dwell_minutes": dwell,
    }


def _eat_to_utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=EAT).astimezone(timezone.utc)


BAR = {"category": "bar"}
DAY_START = _eat_to_utc(2026, 12, 28, 8, 0)


def _nodes_summary(nodes):
    return [(n.venue_name, n.slot_name) for n in nodes]


def test_bar_does_not_fit_morning_tour():
    assert venue_fits_slot(BAR, "morning_tour", list(SLOT_ORDER)) is False
    assert venue_fits_slot({"category": "BAR"}, "morning_tour", list(SLOT_ORDER)) is False
    assert is_afternoon_only_venue(BAR) is True


def test_bar_fits_afternoon_evening_tour_only():
    assert venue_fits_slot(BAR, "afternoon_evening_tour", list(SLOT_ORDER)) is True
    assert venue_fits_slot(BAR, "lunch", list(SLOT_ORDER)) is False
    assert venue_fits_slot(BAR, "dinner", list(SLOT_ORDER)) is False


@pytest.mark.parametrize(
    "category,expected",
    [
        ("temple", {"morning_tour", "afternoon_evening_tour"}),
        ("museum", {"morning_tour", "afternoon_evening_tour"}),
        ("market", {"morning_tour", "afternoon_evening_tour"}),
        ("viewpoint", {"morning_tour", "afternoon_evening_tour"}),
        ("night_market", {"morning_tour", "afternoon_evening_tour"}),
        ("restaurant", {"lunch", "dinner"}),
        ("cafe", {"lunch", "dinner"}),
        ("street_food", {"lunch", "dinner"}),
    ],
)
def test_other_categories_keep_their_slots(category, expected):
    venue = {"category": category}
    fits = {s for s in SLOT_ORDER if venue_fits_slot(venue, s, list(SLOT_ORDER))}
    assert fits == expected
    assert is_afternoon_only_venue(venue) is False


def test_has_matching_slot_for_bar_needs_the_afternoon_slot():
    assert has_matching_slot(BAR, ["morning_tour"]) is False
    assert has_matching_slot(BAR, ["morning_tour", "afternoon_evening_tour"]) is True
    assert has_matching_slot(BAR, ["lunch", "dinner"]) is False
    # Unchanged for a generic activity.
    assert has_matching_slot({"category": "viewpoint"}, ["morning_tour"]) is True


def test_assign_slot_gives_a_bar_the_afternoon_slot():
    slot, remaining = assign_slot(BAR, list(SLOT_ORDER))
    assert slot == "afternoon_evening_tour"
    assert remaining == ["morning_tour", "lunch", "dinner"]
    with pytest.raises(ValueError):
        assign_slot(BAR, ["morning_tour"])
    # A generic activity still takes the earliest activity slot.
    assert assign_slot({"category": "viewpoint"}, list(SLOT_ORDER))[0] == "morning_tour"


def test_whole_day_bar_keeps_the_whole_day_rule():
    whole_day_bar = {"category": "bar", "vibe_tags": ["whole_day"]}
    remaining = ["morning_tour", "lunch", "afternoon_evening_tour"]
    assert venue_fits_slot(whole_day_bar, "morning_tour", remaining) is True
    assert has_matching_slot(whole_day_bar, remaining) is True
    assert assign_slot(whole_day_bar, remaining + ["dinner"]) == ("morning_tour", ["dinner"])


def test_pack_day_never_places_a_bar_in_the_morning():
    bar = _make_venue_row("Probe Beach Bar", _make_hours({}), category="bar")
    views = [
        _make_venue_row(
            "Probe View A", _make_hours({}), category="viewpoint", lat=-5.7223, lng=39.3033
        ),
        _make_venue_row(
            "Probe View B", _make_hours({}), category="viewpoint", lat=-5.7266, lng=39.3097
        ),
    ]
    meals = [
        _make_venue_row(
            "Probe Grill A", _make_hours({}), category="restaurant", lat=-5.7295, lng=39.2914
        ),
        _make_venue_row(
            "Probe Grill B", _make_hours({}), category="restaurant", lat=-5.7286, lng=39.2914
        ),
    ]
    rows = [bar] + views + meals
    nodes, _used = pack_day(rows, 4, DAY_START, GEO, set())
    summary = _nodes_summary(nodes)
    assert nodes, summary
    assert nodes[0].venue_name != bar["name"], summary
    assert nodes[0].venue_name in {v["name"] for v in views}, summary
    for node in nodes:
        if node.venue_name == bar["name"]:
            assert node.slot_name == "afternoon_evening_tour", summary
    assert not [n for n in nodes if n.venue_name == bar["name"] and n.slot_name == "morning_tour"]


def test_pack_day_bar_only_pool_leaves_the_morning_empty():
    bar = _make_venue_row("Probe Beach Bar", _make_hours({}), category="bar")
    meals = [
        _make_venue_row(
            "Probe Grill A", _make_hours({}), category="restaurant", lat=-5.7295, lng=39.2914
        ),
        _make_venue_row(
            "Probe Grill B", _make_hours({}), category="restaurant", lat=-5.7286, lng=39.2914
        ),
    ]
    nodes, _used = pack_day([bar] + meals, 4, DAY_START, GEO, set())
    summary = _nodes_summary(nodes)
    assert not [n for n in nodes if n.slot_name == "morning_tour"], summary
    for node in nodes:
        if node.venue_name == bar["name"]:
            assert node.slot_name == "afternoon_evening_tour", summary


def test_swap_eligibility_rejects_a_bar_for_a_morning_target():
    bar_row = _make_venue_row("Probe Beach Bar", _make_hours({}), category="bar")
    assert is_swap_eligible_venue(bar_row, "morning_tour") is False
    assert is_swap_eligible_venue(bar_row, "afternoon_evening_tour") is True
    assert is_swap_eligible_venue(bar_row, "lunch") is False
    view_row = _make_venue_row("Probe View A", _make_hours({}), category="viewpoint")
    assert is_swap_eligible_venue(view_row, "morning_tour") is True


def test_day_slots_module_is_ascii():
    source = Path(day_slots.__file__).read_text(encoding="utf-8")
    assert source.isascii()
