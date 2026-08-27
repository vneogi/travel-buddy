"""SPEC-29: Pure alert evaluator.

Input: TripState + forecast blocks + injectable now.
Output: List[ContextAlert].

Never calls LLM, network, or modifies itinerary.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from models.alerts import AlertEvidence, ContextAlert, make_alert_id
from models.schemas import NodeStatus, TripNode, TripState
from services.weather_provider import ForecastBlock

# Storm codes from existing WeatherThresholds
STORM_CODES = {200, 201, 202, 210, 211, 212, 221, 230, 231, 232, 771, 781}


def evaluate_alerts(
    trip: TripState,
    forecast_blocks: List[ForecastBlock],
    source_updated_at: datetime,
    now: Optional[datetime] = None,
    location_basis: str = "trip_region",
) -> List[ContextAlert]:
    """Evaluate forecast blocks against trip nodes. Pure, deterministic."""
    if now is None:
        now = datetime.now(tz=timezone.utc)

    # Only consider pending, non-skipped nodes
    eligible_nodes = [
        n for n in trip.nodes if n.status != NodeStatus.SKIPPED and n.status == NodeStatus.PENDING
    ]
    if not eligible_nodes or not forecast_blocks:
        return []

    alerts: List[ContextAlert] = []
    seen_ids: set = set()

    for block in forecast_blocks:
        block_start = block.dt
        block_end = block.dt + timedelta(hours=3)

        affected = []
        for node in eligible_nodes:
            node_start = node.scheduled_start
            node_end = node_start + timedelta(minutes=node.duration_minutes)
            if node_start < block_end and node_end > block_start:
                affected.append(node)

        if not affected:
            continue

        node_ids = [n.node_id for n in affected]
        node_names = [n.venue_name for n in affected]
        valid_from = block_start
        valid_until = block_end
        expires_at = block_end + timedelta(minutes=30)

        block_alerts = _evaluate_block(
            block,
            trip.trip_id,
            node_ids,
            node_names,
            source_updated_at,
            valid_from,
            valid_until,
            expires_at,
            location_basis,
            trip.geo_region,
        )

        for alert in block_alerts:
            if alert.alert_id not in seen_ids:
                seen_ids.add(alert.alert_id)
                alerts.append(alert)

    return alerts


def _evaluate_block(
    block: ForecastBlock,
    trip_id: str,
    node_ids: List[str],
    node_names: List[str],
    source_updated_at: datetime,
    valid_from: datetime,
    valid_until: datetime,
    expires_at: datetime,
    location_basis: str,
    geo_region: Optional[str],
) -> List[ContextAlert]:
    """Evaluate a single forecast block against thresholds."""
    alerts: List[ContextAlert] = []

    # Extreme heat warning: feels_like >= 45
    if block.feels_like_c >= 45:
        names_str = ", ".join(node_names)
        alert_id = make_alert_id(trip_id, "extreme_heat", valid_from, node_ids)
        alerts.append(
            ContextAlert(
                alert_id=alert_id,
                alert_type="extreme_heat",
                severity="warning",
                message=(
                    f"Feels like {block.feels_like_c:.0f} C during {names_str}. "
                    "If you will be outdoors, seek shade, carry water, and consider shortening outdoor time."
                ),
                affected_node_ids=node_ids,
                affected_node_names=node_names,
                source="openweather",
                source_updated_at=source_updated_at,
                valid_from=valid_from,
                valid_until=valid_until,
                expires_at=expires_at,
                location_basis=location_basis,
                geo_region=geo_region,
                evidence=AlertEvidence(
                    feels_like_c=block.feels_like_c,
                    temp_c=block.temp_c,
                    humidity=block.humidity,
                    condition_code=block.condition_code,
                ),
                suggested_action="seek_shade_and_water",
            )
        )
    elif block.feels_like_c >= 40:
        names_str = ", ".join(node_names)
        alert_id = make_alert_id(trip_id, "high_heat", valid_from, node_ids)
        alerts.append(
            ContextAlert(
                alert_id=alert_id,
                alert_type="high_heat",
                severity="advisory",
                message=(
                    f"Feels like {block.feels_like_c:.0f} C during {names_str}. "
                    "If you will be outdoors, consider shorter exposure or shaded venues."
                ),
                affected_node_ids=node_ids,
                affected_node_names=node_names,
                source="openweather",
                source_updated_at=source_updated_at,
                valid_from=valid_from,
                valid_until=valid_until,
                expires_at=expires_at,
                location_basis=location_basis,
                geo_region=geo_region,
                evidence=AlertEvidence(
                    feels_like_c=block.feels_like_c,
                    temp_c=block.temp_c,
                    humidity=block.humidity,
                    condition_code=block.condition_code,
                ),
                suggested_action="review_outdoor_plans",
            )
        )

    # Storm warning
    if block.condition_code in STORM_CODES:
        alert_id = make_alert_id(trip_id, "storm", valid_from, node_ids)
        names_str = ", ".join(node_names)
        alerts.append(
            ContextAlert(
                alert_id=alert_id,
                alert_type="storm",
                severity="warning",
                message=(
                    f"Thunderstorm conditions forecast during {names_str}. Outdoor plans may be unsafe."
                ),
                affected_node_ids=node_ids,
                affected_node_names=node_names,
                source="openweather",
                source_updated_at=source_updated_at,
                valid_from=valid_from,
                valid_until=valid_until,
                expires_at=expires_at,
                location_basis=location_basis,
                geo_region=geo_region,
                evidence=AlertEvidence(
                    condition_code=block.condition_code,
                    rain_probability=block.rain_probability,
                ),
                suggested_action="review_outdoor_plans",
            )
        )
    elif block.rain_probability >= 0.50:
        alert_id = make_alert_id(trip_id, "rain", valid_from, node_ids)
        names_str = ", ".join(node_names)
        pct = int(block.rain_probability * 100)
        alerts.append(
            ContextAlert(
                alert_id=alert_id,
                alert_type="rain",
                severity="advisory",
                message=(
                    f"{pct}% chance of rain during {names_str}. Review plans that require outdoor time."
                ),
                affected_node_ids=node_ids,
                affected_node_names=node_names,
                source="openweather",
                source_updated_at=source_updated_at,
                valid_from=valid_from,
                valid_until=valid_until,
                expires_at=expires_at,
                location_basis=location_basis,
                geo_region=geo_region,
                evidence=AlertEvidence(
                    rain_probability=block.rain_probability,
                    condition_code=block.condition_code,
                ),
                suggested_action="review_outdoor_plans",
            )
        )

    # High humidity info: humidity >= 80 AND feels_like >= 35 (but < 40)
    if block.humidity >= 80 and block.feels_like_c >= 35 and block.feels_like_c < 40:
        alert_id = make_alert_id(trip_id, "high_humidity", valid_from, node_ids)
        names_str = ", ".join(node_names)
        alerts.append(
            ContextAlert(
                alert_id=alert_id,
                alert_type="high_humidity",
                severity="info",
                message=(
                    f"High humidity ({block.humidity}%) with "
                    f"{block.feels_like_c:.0f} C feels-like during {names_str}. "
                    "Stay hydrated."
                ),
                affected_node_ids=node_ids,
                affected_node_names=node_names,
                source="openweather",
                source_updated_at=source_updated_at,
                valid_from=valid_from,
                valid_until=valid_until,
                expires_at=expires_at,
                location_basis=location_basis,
                geo_region=geo_region,
                evidence=AlertEvidence(
                    humidity=block.humidity,
                    feels_like_c=block.feels_like_c,
                    temp_c=block.temp_c,
                ),
                suggested_action=None,
            )
        )

    return alerts
