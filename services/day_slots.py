"""SPEC-41: Named day slots and travel-day remaining slot computation.

The default full in-city day has four named slots in order:

    morning_tour -> lunch -> afternoon_evening_tour -> dinner

Breakfast is not a default generated slot.  Locked bookings (flights,
trains, hotels, tours) keep exact destination-local timestamps; the slot
names here are for flexible catalog-packed nodes only.
"""

from __future__ import annotations

from typing import List, Tuple

from datetime import datetime

# Ordered default slots for a full in-city day (SPEC-41).
SLOT_ORDER: Tuple[str, ...] = (
    "morning_tour",
    "lunch",
    "afternoon_evening_tour",
    "dinner",
)

# Food (restaurant) slot names, earliest-first.
_FOOD_SLOTS: Tuple[str, ...] = ("lunch", "dinner")

# Activity (sights, walks, markets, etc.) slot names, earliest-first.
_ACTIVITY_SLOTS: Tuple[str, ...] = ("morning_tour", "afternoon_evening_tour")

# Categories that map to a food slot.
_FOOD_CATEGORIES: frozenset = frozenset({"cafe", "restaurant", "street_food"})

# Vibe tags that identify a whole-day excursion.
# A whole-day excursion occupies morning + lunch + afternoon simultaneously;
# only dinner may be generated afterward.
WHOLE_DAY_VIBE_TAGS: frozenset = frozenset(
    {
        "whole_day",
        "full_day_tour",
        "canyoneering",
        "island_hopping",
        "out_of_city_tour",
        "day_trip",
    }
)

# Slots consumed by a whole-day excursion.
_WHOLE_DAY_CONSUMED: frozenset = frozenset({"morning_tour", "lunch", "afternoon_evening_tour"})


def slot_from_time(slot: datetime, geo_region: str) -> str:
    """Determine a slot name from a destination-local scheduled start time.

    Used for default (unconstrained) days where slot names are a rendering
    label, not a packing constraint.  The cut-offs are coarse on purpose:
    before 11:00 is morning, 11:00-13:59 is lunch, 14:00-16:59 is
    afternoon/evening, and 17:00+ is dinner.
    """
    from services.destination_tz import destination_tz as _dest_tz

    tz = _dest_tz(geo_region)
    local = slot.astimezone(tz) if tz is not None else slot
    hour = local.hour
    if hour < 11:
        return "morning_tour"
    elif hour < 14:
        return "lunch"
    elif hour < 17:
        return "afternoon_evening_tour"
    else:
        return "dinner"


def is_food_venue(venue: dict) -> bool:
    """True if the venue should occupy a food (lunch/dinner) slot."""
    return (venue.get("category") or "experience").lower() in _FOOD_CATEGORIES


def is_whole_day_excursion(venue: dict) -> bool:
    """True if the venue is a whole-day trip (canyoneering, island-hopping, etc.)."""
    tags = frozenset(t.lower() for t in (venue.get("vibe_tags") or []))
    return bool(tags & WHOLE_DAY_VIBE_TAGS)


def has_matching_slot(venue: dict, remaining_slots: List[str]) -> bool:
    """True if *venue* can be assigned the slots it needs from *remaining_slots*.

    A whole-day excursion needs *all* of its consumed slots to be present
    (morning, lunch, afternoon); a partial set is not enough.
    """
    if is_whole_day_excursion(venue):
        return all(s in remaining_slots for s in _WHOLE_DAY_CONSUMED)
    if is_food_venue(venue):
        return any(s in remaining_slots for s in _FOOD_SLOTS)
    return any(s in remaining_slots for s in _ACTIVITY_SLOTS)


def assign_slot(
    venue: dict,
    remaining_slots: List[str],
) -> Tuple[str, List[str]]:
    """Assign the earliest matching slot from *remaining_slots*.

    Returns ``(slot_name, updated_remaining_slots)``.
    Raises ``ValueError`` if no matching slot is available.

    A whole-day excursion consumes ``morning_tour``, ``lunch``, and
    ``afternoon_evening_tour`` simultaneously; its ``slot_name`` is
    ``"morning_tour"`` (the first consumed slot that is still present).
    """
    if is_whole_day_excursion(venue):
        if not all(s in remaining_slots for s in _WHOLE_DAY_CONSUMED):
            raise ValueError("No whole-day slots available")
        slot = next(s for s in SLOT_ORDER if s in remaining_slots and s in _WHOLE_DAY_CONSUMED)
        new_remaining = [s for s in remaining_slots if s not in _WHOLE_DAY_CONSUMED]
        return slot, new_remaining

    if is_food_venue(venue):
        for s in _FOOD_SLOTS:
            if s in remaining_slots:
                new_remaining = list(remaining_slots)
                new_remaining.remove(s)
                return s, new_remaining
        raise ValueError("No food slot available")

    # Activity venue.
    for s in _ACTIVITY_SLOTS:
        if s in remaining_slots:
            new_remaining = list(remaining_slots)
            new_remaining.remove(s)
            return s, new_remaining
    raise ValueError("No activity slot available")


def venue_fits_slot(venue: dict, target_slot: str, remaining_slots: List[str]) -> bool:
    """True if *venue* can fill the specific *target_slot*.

    - Whole-day excursion: only when target is ``morning_tour`` and all
      consumed slots (morning, lunch, afternoon) are still available.
    - Food venue (cafe/restaurant/street_food): target must be a food slot.
    - Activity venue: target must be an activity slot.
    """
    if is_whole_day_excursion(venue):
        return target_slot == "morning_tour" and all(
            s in remaining_slots for s in _WHOLE_DAY_CONSUMED
        )
    if is_food_venue(venue):
        return target_slot in _FOOD_SLOTS
    return target_slot in _ACTIVITY_SLOTS


def compute_remaining_slots(
    booking_local_hour: int,
    booking_type: str | None,
    has_hotel: bool,
) -> List[str]:
    """Conservative remaining slots after a travel booking on the same local day.

    Parameters
    ----------
    booking_local_hour:
        Destination-local hour (0-23) of the arrival or departure event.
    booking_type:
        ``"flight"``, ``"train"``, ``"hotel"``, ``"tour"``, or ``None``.
    has_hotel:
        Whether the day has a hotel booking (True when ``booking_type == "hotel"``
        or when a hotel check-in exists alongside a different primary booking).
        A hotel booking before noon signals checkout-day: only the morning
        activity slot remains available.

    Conservative defaults (HITL intent to restore extra slots is out of
    this slice):

    - hotel checkout (has_hotel + hotel booking + hour < 12) -> morning only
    - arrival >= 17:00                      -> dinner only
    - arrival 14:00-16:59                   -> afternoon_evening_tour, dinner
    - morning departure flight/train < 12   -> lunch, afternoon_evening_tour, dinner
    - otherwise                             -> full SLOT_ORDER
    """
    # Hotel checkout: booking IS a hotel that starts before noon -> morning only.
    if has_hotel and booking_type == "hotel" and booking_local_hour < 12:
        return ["morning_tour"]

    # Early-evening or late arrival: dinner only.
    if booking_local_hour >= 17:
        return ["dinner"]

    # Mid-afternoon arrival: evening show + dinner (never a morning tour).
    if booking_local_hour >= 14:
        return ["afternoon_evening_tour", "dinner"]

    # Morning departure (flight or train, before noon): no morning tour.
    if booking_type in ("flight", "train") and booking_local_hour < 12:
        return ["lunch", "afternoon_evening_tour", "dinner"]

    # Full day.
    return list(SLOT_ORDER)
