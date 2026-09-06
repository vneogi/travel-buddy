"""SPEC-35 Phase A: pure departure-candidate evaluator.

Stateless. No LLM, no mutation, no event emission, no quota consumption.
All side-effect-producing dependencies (route provider, weather provider)
are injected so the evaluator is fully testable with stubs.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from config.regions import REGIONS
from models.notifications import (
    DepartureEvidence,
    NotificationCandidate,
    PolicyBuffers,
    RouteEvidence,
    WeatherEvidence,
)
from models.schemas import NodeStatus, TripNode, TripState
from services.route_provider import RouteProvider, RouteProviderError, RouteResult
from services.weather_provider import ForecastBlock, WeatherProvider, WeatherProviderError

EVALUATOR_VERSION = "departure_v1"
ARRIVAL_BUFFER_MINUTES = 10
WEATHER_BUFFER_MINUTES = 10
RAIN_THRESHOLD = 0.50
ELIGIBLE_LEAD_MINUTES = 10
EXPIRY_AFTER_START_MINUTES = 15
ROUTE_FRESHNESS_SECONDS = 300  # 5 minutes


def deterministic_id(
    trip_id: str,
    notification_type: str,
    node_id: str,
    scheduled_start: datetime,
) -> str:
    """SPEC-35: deterministic notification ID from key fields."""
    raw = (
        f"{trip_id}:{notification_type}:{node_id}:{scheduled_start.isoformat()}:{EVALUATOR_VERSION}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _next_pending_node(nodes: List[TripNode], now: datetime) -> Optional[TripNode]:
    """Select only the next future pending, non-skipped node."""
    candidates = [
        n
        for n in nodes
        if n.status in (NodeStatus.PENDING,)
        and n.scheduled_start > now - timedelta(minutes=EXPIRY_AFTER_START_MINUTES)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda n: n.scheduled_start)
    return candidates[0]


def _find_origin_node(nodes: List[TripNode], dest_node: TripNode) -> Optional[TripNode]:
    """Find an origin: the active or immediately preceding node with coords.

    Trip-region centre is NOT a valid departure origin (per SPEC-35).
    """
    preceding = []
    for n in nodes:
        if n.node_id == dest_node.node_id:
            continue
        if n.lat is None or n.lng is None:
            continue
        if n.status == NodeStatus.ACTIVE:
            return n  # Active node always wins
        if n.scheduled_start < dest_node.scheduled_start:
            preceding.append(n)
    if preceding:
        preceding.sort(key=lambda n: n.scheduled_start, reverse=True)
        return preceding[0]
    return None


def _resolve_region_tz(node: TripNode, trip: TripState) -> Optional[ZoneInfo]:
    """Get the IANA timezone for a node from its region or the trip region."""
    region_code = node.geo_region or trip.geo_region
    region = REGIONS.get(region_code)
    if region is None or not region.timezone:
        return None
    return ZoneInfo(region.timezone)


def _rain_probability_for_window(
    blocks: List[ForecastBlock],
    window_start: datetime,
    window_end: datetime,
) -> float:
    """Max rain probability across forecast blocks overlapping the window."""
    max_prob = 0.0
    for block in blocks:
        block_start = block.dt
        block_end = block_start + timedelta(hours=3)
        if block_start < window_end and block_end > window_start:
            max_prob = max(max_prob, block.rain_probability)
    return max_prob


def _format_departure_message(
    venue_name: str,
    traffic_minutes: int,
    rain_buffer: int,
    arrival_buffer: int,
    departure_local_str: str,
    is_overdue: bool,
    has_rain: bool,
) -> str:
    """Build the notification message copy."""
    parts = []
    if is_overdue:
        parts.append(f"Leave now for {venue_name}.")
    else:
        parts.append(f"Leave for {venue_name} by {departure_local_str}.")
    parts.append(f"The drive is about {traffic_minutes} minutes by road")
    if has_rain:
        parts[-1] += f"; {rain_buffer} extra minutes added for forecast rain."
    else:
        parts[-1] += "."
    return " ".join(parts)


async def evaluate_departure(
    trip: TripState,
    now: datetime,
    route_provider: RouteProvider,
    weather_provider: WeatherProvider,
) -> Tuple[Optional[NotificationCandidate], Optional[str]]:
    """Evaluate a departure candidate for the trip.

    Returns (candidate_or_None, error_detail_or_None).
    Never raises; provider errors are returned as partial status detail.
    No LLM, no mutation, no event, no quota.
    """
    # 1. Schedule-time gate
    if trip.schedule_basis != "region_local_v1":
        return None, "legacy_trip_no_schedule_basis"

    # 2. Next pending node
    dest = _next_pending_node(trip.nodes, now)
    if dest is None:
        return None, None

    # 3. Destination timezone
    dest_tz = _resolve_region_tz(dest, trip)
    if dest_tz is None:
        return None, "no_region_timezone"

    # 4. Destination coordinates
    if dest.lat is None or dest.lng is None:
        return None, "no_destination_coordinates"

    # 5. Origin coordinates
    origin = _find_origin_node(trip.nodes, dest)
    if origin is None:
        return None, "no_credible_origin"

    # 6. Route provider call
    route_result: Optional[RouteResult] = None
    route_error: Optional[str] = None
    try:
        route_result = await route_provider.get_driving_duration(
            origin_lat=origin.lat,
            origin_lng=origin.lng,
            dest_lat=dest.lat,
            dest_lng=dest.lng,
            departure_time=dest.scheduled_start,
        )
    except RouteProviderError as exc:
        route_error = str(exc)

    if route_result is None:
        return None, f"route_unavailable:{route_error or 'unknown'}"

    observed_at = route_result.observed_at
    if observed_at.tzinfo is None:
        return None, "route_unavailable:route_evidence_missing_timezone"
    route_age_seconds = (now - observed_at.astimezone(timezone.utc)).total_seconds()
    if route_age_seconds > ROUTE_FRESHNESS_SECONDS:
        return None, "route_unavailable:stale_route_evidence"

    # 7. Weather for rain buffer (reuse existing SPEC-29 provider)
    rain_prob = 0.0
    weather_observed_at = None
    weather_source = None
    try:
        blocks, weather_obs = await weather_provider.get_forecast(dest.lat, dest.lng)
        if blocks:
            depart_window_start = dest.scheduled_start - timedelta(
                minutes=route_result.traffic_duration_minutes + ARRIVAL_BUFFER_MINUTES + 30
            )
            rain_prob = _rain_probability_for_window(
                blocks, depart_window_start, dest.scheduled_start
            )
            weather_observed_at = weather_obs
            weather_source = "openweather"
    except WeatherProviderError:
        pass  # Weather failure does not suppress departure candidate

    # 8. Calculate recommended departure
    weather_buffer = WEATHER_BUFFER_MINUTES if rain_prob >= RAIN_THRESHOLD else 0
    total_lead = route_result.traffic_duration_minutes + ARRIVAL_BUFFER_MINUTES + weather_buffer
    recommended_departure = dest.scheduled_start - timedelta(minutes=total_lead)

    # 9. Eligibility and expiry
    eligible_at = recommended_departure - timedelta(minutes=ELIGIBLE_LEAD_MINUTES)
    expires_at = dest.scheduled_start + timedelta(minutes=EXPIRY_AFTER_START_MINUTES)

    # 10. Check eligibility window
    if now < eligible_at:
        return None, None  # Not yet eligible
    if now > expires_at:
        return None, None  # Expired

    # 11. Format copy in destination timezone
    departure_local = recommended_departure.astimezone(dest_tz)
    departure_local_str = departure_local.strftime("%H:%M")
    is_overdue = now >= recommended_departure

    if is_overdue:
        title = f"Leave now for {dest.venue_name}"
    else:
        title = f"Time to head to {dest.venue_name}"

    message = _format_departure_message(
        venue_name=dest.venue_name,
        traffic_minutes=route_result.traffic_duration_minutes,
        rain_buffer=weather_buffer,
        arrival_buffer=ARRIVAL_BUFFER_MINUTES,
        departure_local_str=departure_local_str,
        is_overdue=is_overdue,
        has_rain=weather_buffer > 0,
    )

    # 12. Build evidence
    route_evidence = RouteEvidence(
        source=route_result.source,
        observed_at=route_result.observed_at,
        normal_duration_minutes=route_result.normal_duration_minutes,
        traffic_duration_minutes=route_result.traffic_duration_minutes,
        mode=route_result.mode,
        origin_basis="previous_node",
    )

    weather_evidence = None
    if weather_source and weather_observed_at is not None:
        weather_evidence = WeatherEvidence(
            source=weather_source,
            observed_at=weather_observed_at,
            rain_probability=rain_prob,
        )

    evidence = DepartureEvidence(
        route=route_evidence,
        weather=weather_evidence,
        policy=PolicyBuffers(
            arrival_buffer_minutes=ARRIVAL_BUFFER_MINUTES,
            weather_buffer_minutes=weather_buffer,
        ),
    )

    # 13. Deterministic ID
    notif_id = deterministic_id(
        trip.trip_id, "departure_reminder", dest.node_id, dest.scheduled_start
    )

    candidate = NotificationCandidate(
        notification_id=notif_id,
        type="departure_reminder",
        priority="trip_critical",
        node_id=dest.node_id,
        title=title,
        message=message,
        eligible_at=eligible_at,
        expires_at=expires_at,
        recommended_departure_at=recommended_departure,
        time_zone=str(dest_tz),
        deep_link=f"/trip/{trip.trip_id}/node/{dest.node_id}",
        evidence=evidence,
    )

    return candidate, None
