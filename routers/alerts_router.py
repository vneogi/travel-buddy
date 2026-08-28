"""SPEC-29: Context alerts endpoint.

GET /api/v1/trip/{trip_id}/alerts
- Never mutates trip state.
- Never consumes reroute quota.
- Never calls LLM / RAG / state machine.
"""

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from config.regions import REGIONS
from models.alerts import TripAlertsResponse
from models.schemas import NodeStatus
from security import get_current_user_id, require_trip_owner
from services.alert_evaluator import evaluate_alerts
from services.db_provider import db_service
from services.weather_provider import WeatherProvider, WeatherProviderError

router = APIRouter(prefix="/api/v1")

_weather_provider = WeatherProvider()


def get_weather_provider() -> WeatherProvider:
    """Dependency for test injection."""
    return _weather_provider


@router.get("/trip/{trip_id}/alerts", response_model=TripAlertsResponse)
async def get_trip_alerts(
    trip_id: str,
    user_id: str = Depends(get_current_user_id),
    provider: WeatherProvider = Depends(get_weather_provider),
):
    trip = db_service.get_trip(trip_id)
    require_trip_owner(trip, user_id)

    now = datetime.now(tz=timezone.utc)

    if not provider.is_configured:
        return TripAlertsResponse(
            trip_id=trip_id,
            status="unconfigured",
            alerts=[],
            refreshed_at=now,
        ).model_dump(mode="json")

    # D5: Group future pending nodes by geo_region.
    eligible = [
        n for n in trip.nodes if n.status == NodeStatus.PENDING and n.scheduled_start >= now
    ]
    region_groups: dict = defaultdict(list)
    for node in eligible:
        region_key = node.geo_region or trip.geo_region or ""
        region_groups[region_key].append(node)

    all_alerts = []
    for region_key, nodes in region_groups.items():
        # Find coordinates: first node with lat/lng, else region center.
        lat, lng = None, None
        location_basis = "trip_region"
        for n in nodes:
            if n.lat is not None and n.lng is not None:
                lat, lng = n.lat, n.lng
                location_basis = "node_coordinates"
                break
        if lat is None or lng is None:
            region = REGIONS.get(region_key)
            if region:
                lat, lng = region.default_lat, region.default_lng
                location_basis = "trip_region"
            else:
                # Unknown region with no coordinates: skip honestly.
                continue

        try:
            forecast_blocks, source_updated_at = await provider.get_forecast(lat, lng)
        except WeatherProviderError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "weather_provider_unavailable",
                    "message": "Weather data temporarily unavailable.",
                },
            ) from exc

        # Build a temporary trip state scoped to this region's nodes
        # for evaluate_alerts.
        from copy import deepcopy

        region_trip = deepcopy(trip)
        region_trip.nodes = nodes

        region_alerts = evaluate_alerts(
            region_trip,
            forecast_blocks,
            source_updated_at,
            now=now,
            location_basis=location_basis,
        )
        # Tag alerts with the region
        for a in region_alerts:
            a.geo_region = region_key or None
        all_alerts.extend(region_alerts)

    # Filter expired and deduplicate by alert_id
    seen_ids = set()
    final_alerts = []
    for a in all_alerts:
        if a.expires_at > now and a.alert_id not in seen_ids:
            seen_ids.add(a.alert_id)
            final_alerts.append(a)

    return TripAlertsResponse(
        trip_id=trip_id,
        status="available",
        alerts=final_alerts,
        refreshed_at=now,
    )
