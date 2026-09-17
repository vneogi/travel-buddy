"""SPEC-10 booking-anchor constraints.

Named constants and shared predicates used by:
  - services/scheduler.py  (reschedule_and_validate)
  - agents/state_machine.py  (swap search/apply, add_booking)

pack_day flight/hotel constraints remain deferred.

No randomness, no server clock, no network, no LLM.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from models.schemas import NodeStatus, TripNode
from services.destination_tz import destination_tz as _dest_tz

# ---------------------------------------------------------------------------
# Naive-datetime guard
# ---------------------------------------------------------------------------


def _ensure_aware(dt: datetime) -> datetime:
    """Return *dt* with UTC tzinfo when naive; passthrough otherwise."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _local_date_of(dt: datetime, geo_region: str):
    """Destination-local date of *dt* in *geo_region*."""
    aware = _ensure_aware(dt)
    tz = _dest_tz(geo_region)
    if tz is not None:
        return aware.astimezone(tz).date()
    return aware.date()


# ---------------------------------------------------------------------------
# Named constants  (tests must fail if these are removed)
# ---------------------------------------------------------------------------

PRE_FLIGHT_BUFFER_MINUTES: int = 150
"""Minutes before a locked flight during which no activity may end.

Spec example: 07:00 local flight => cutoff at 04:30 local.
"""

HOTEL_RETURN_LOCAL_HOUR: int = 21
"""Destination-local hour by which the last activity must allow walk-back
to the covering hotel on each covered night."""


# ---------------------------------------------------------------------------
# Flight: preceding-evening cutoff
# ---------------------------------------------------------------------------


def is_locked_flight(node: TripNode) -> bool:
    """True for locked flight bookings."""
    return (
        node.is_locked
        and getattr(node, "node_kind", "activity") == "booking"
        and getattr(node, "booking_type", None) == "flight"
    )


def flight_cutoff(flight: TripNode) -> datetime:
    """Absolute UTC cutoff before which all preceding activities must end.

    cutoff = flight.scheduled_start - PRE_FLIGHT_BUFFER_MINUTES
    """
    return _ensure_aware(flight.scheduled_start) - timedelta(minutes=PRE_FLIGHT_BUFFER_MINUTES)


def violates_flight_cutoff(
    activity_start: datetime,
    activity_duration: int,
    flight: TripNode,
    *,
    activity_lat: Optional[float] = None,
    activity_lng: Optional[float] = None,
) -> bool:
    """True when an activity would breach the pre-flight buffer.

    Uses the stricter of buffer-cutoff and walking-to-flight when both
    the activity and the flight have coordinates.  Missing coords on
    either side: still enforce the 150-minute buffer.
    """
    import math

    from services.transit import walking_minutes as _walking_minutes

    act_start = _ensure_aware(activity_start)
    activity_end = act_start + timedelta(minutes=activity_duration)
    cutoff = flight_cutoff(flight)
    fl_start = _ensure_aware(flight.scheduled_start)

    # Buffer test (always enforced)
    if activity_end > cutoff:
        return True

    # Walking test (stricter when coords exist on both sides)
    flight_has_coords = (
        flight.lat is not None
        and flight.lng is not None
        and math.isfinite(flight.lat)
        and math.isfinite(flight.lng)
    )
    act_has_coords = (
        activity_lat is not None
        and activity_lng is not None
        and math.isfinite(activity_lat)
        and math.isfinite(activity_lng)
    )
    if flight_has_coords and act_has_coords:
        walk = _walking_minutes(activity_lat, activity_lng, flight.lat, flight.lng)
        if activity_end + timedelta(minutes=walk) > fl_start:
            return True

    return False


def find_constraining_flight(
    nodes: List[TripNode],
    activity: TripNode,
) -> Optional[TripNode]:
    """Return the earliest locked flight that constrains *activity*.

    Rules:
      - Flight must be AFTER the activity in schedule order.
      - Same geo_region.
      - Flight's local date is the same local day as the activity OR the
        immediately following local day (cross-midnight).
      - Among qualifying flights, pick the earliest by scheduled_start,
        then node_id for determinism.
    """
    act_region = getattr(activity, "geo_region", None)
    if not act_region:
        return None

    act_start = _ensure_aware(activity.scheduled_start)
    act_local_date = _local_date_of(act_start, act_region)

    best: Optional[TripNode] = None
    for node in nodes:
        if not is_locked_flight(node):
            continue
        fl_region = getattr(node, "geo_region", None)
        if fl_region != act_region:
            continue
        fl_start = _ensure_aware(node.scheduled_start)
        # Flight must be after the activity
        if fl_start <= act_start:
            continue
        fl_local_date = _local_date_of(fl_start, act_region)
        delta_days = (fl_local_date - act_local_date).days
        if delta_days not in (0, 1):
            continue
        # Eligible -- pick earliest, then node_id
        if best is None:
            best = node
        else:
            best_start = _ensure_aware(best.scheduled_start)
            if fl_start < best_start:
                best = node
            elif fl_start == best_start and node.node_id < best.node_id:
                best = node
    return best


# ---------------------------------------------------------------------------
# Hotel: daily geographic anchor
# ---------------------------------------------------------------------------


def is_hotel_booking(node: TripNode) -> bool:
    """True for hotel bookings (background anchors)."""
    return (
        getattr(node, "node_kind", "activity") == "booking"
        and getattr(node, "booking_type", None) == "hotel"
    )


def hotel_covered_dates(hotel: TripNode, geo_region: str) -> list:
    """Return the list of destination-local dates the hotel covers.

    Coverage: [check_in_local_date, checkout_local_date).
    Checkout date is NOT a covered night.
    """
    start = _ensure_aware(hotel.scheduled_start)
    tz = _dest_tz(geo_region)
    if tz is not None:
        checkin_local = start.astimezone(tz)
    else:
        checkin_local = start
    checkout_utc = start + timedelta(minutes=hotel.duration_minutes)
    if tz is not None:
        checkout_local = checkout_utc.astimezone(tz)
    else:
        checkout_local = checkout_utc

    dates = []
    d = checkin_local.date()
    while d < checkout_local.date():
        dates.append(d)
        d += timedelta(days=1)
    return dates


def find_covering_hotel(
    nodes: List[TripNode],
    geo_region: str,
    local_date,
) -> Optional[TripNode]:
    """Return the hotel that covers *local_date*, if any.

    If two hotels overlap, prefer later check-in, then node_id (deterministic).
    """
    best: Optional[TripNode] = None
    for node in nodes:
        if not is_hotel_booking(node):
            continue
        node_region = getattr(node, "geo_region", None)
        if node_region and node_region != geo_region:
            continue
        if local_date in hotel_covered_dates(node, geo_region):
            if best is None:
                best = node
            else:
                if node.scheduled_start > best.scheduled_start:
                    best = node
                elif node.scheduled_start == best.scheduled_start and node.node_id > best.node_id:
                    best = node
    return best


def hotel_evening_wall(hotel: TripNode, geo_region: str, local_date) -> datetime:
    """Return the UTC instant of HOTEL_RETURN_LOCAL_HOUR on *local_date*."""
    tz = _dest_tz(geo_region)
    if tz is not None:
        wall_local = datetime(
            local_date.year,
            local_date.month,
            local_date.day,
            HOTEL_RETURN_LOCAL_HOUR,
            0,
            0,
            tzinfo=tz,
        )
        return wall_local.astimezone(timezone.utc)
    else:
        return datetime(
            local_date.year,
            local_date.month,
            local_date.day,
            HOTEL_RETURN_LOCAL_HOUR,
            0,
            0,
            tzinfo=timezone.utc,
        )


def violates_hotel_return(
    activity_start: datetime,
    activity_duration: int,
    hotel: TripNode,
    geo_region: str,
    local_date,
    *,
    activity_lat: Optional[float] = None,
    activity_lng: Optional[float] = None,
) -> bool:
    """True when the activity cannot walk back to the hotel by the evening wall.

    Missing hotel or activity coords: returns True (ineligible for last
    slot rather than assuming zero walking).
    """
    import math

    from services.transit import walking_minutes as _walking_minutes

    act_start = _ensure_aware(activity_start)
    activity_end = act_start + timedelta(minutes=activity_duration)
    wall = hotel_evening_wall(hotel, geo_region, local_date)

    hotel_has_coords = (
        hotel.lat is not None
        and hotel.lng is not None
        and math.isfinite(hotel.lat)
        and math.isfinite(hotel.lng)
    )
    act_has_coords = (
        activity_lat is not None
        and activity_lng is not None
        and math.isfinite(activity_lat)
        and math.isfinite(activity_lng)
    )

    if not hotel_has_coords or not act_has_coords:
        return True  # missing coords -> ineligible for last slot

    walk = _walking_minutes(activity_lat, activity_lng, hotel.lat, hotel.lng)
    return activity_end + timedelta(minutes=walk) > wall


def local_09_utc(geo_region: str, local_date) -> datetime:
    """Return the UTC instant of 09:00 destination-local on *local_date*."""
    tz = _dest_tz(geo_region)
    if tz is not None:
        morning_local = datetime(
            local_date.year,
            local_date.month,
            local_date.day,
            9,
            0,
            0,
            tzinfo=tz,
        )
        return morning_local.astimezone(timezone.utc)
    return datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        9,
        0,
        0,
        tzinfo=timezone.utc,
    )


def hotel_morning_origin(
    hotel: TripNode,
    geo_region: str,
    local_date,
) -> Optional[datetime]:
    """UTC instant from which the first activity of *local_date*
    should compute walking departure from the hotel.

    On the check-in local day: use hotel.scheduled_start (the check-in
    instant).  Activities scheduled before that instant are not shifted.
    On later covered mornings: use destination-local 09:00 converted to UTC.

    Returns None if the hotel does not cover *local_date*.
    """
    if local_date not in hotel_covered_dates(hotel, geo_region):
        return None

    start = _ensure_aware(hotel.scheduled_start)
    tz = _dest_tz(geo_region)
    if tz is not None:
        checkin_local_date = start.astimezone(tz).date()
    else:
        checkin_local_date = start.date()

    if local_date == checkin_local_date:
        return start
    return local_09_utc(geo_region, local_date)


def is_first_unlocked_activity(
    node: TripNode,
    all_nodes: List[TripNode],
    geo_region: str,
    local_date,
) -> bool:
    """True when *node* is the first unlocked non-booking activity on
    *local_date* in *geo_region* (excludes skipped/locked/bookings)."""
    for n in all_nodes:
        if n.node_id == node.node_id:
            return True
        if n.status == NodeStatus.SKIPPED:
            continue
        if n.is_locked:
            continue
        if getattr(n, "node_kind", "activity") == "booking":
            continue
        n_region = getattr(n, "geo_region", None)
        if n_region != geo_region:
            continue
        n_date = _local_date_of(_ensure_aware(n.scheduled_start), geo_region)
        if n_date == local_date:
            return False  # found an earlier unlocked activity
    return True


def is_last_unlocked_activity(
    node: TripNode,
    all_nodes: List[TripNode],
    geo_region: str,
    local_date,
) -> bool:
    """True when *node* is the last unlocked non-booking activity on
    *local_date* in *geo_region*."""
    last = None
    for n in all_nodes:
        if n.status == NodeStatus.SKIPPED:
            continue
        if n.is_locked:
            continue
        if getattr(n, "node_kind", "activity") == "booking":
            continue
        n_region = getattr(n, "geo_region", None)
        if n_region != geo_region:
            continue
        n_date = _local_date_of(_ensure_aware(n.scheduled_start), geo_region)
        if n_date == local_date:
            last = n
    return last is not None and last.node_id == node.node_id
