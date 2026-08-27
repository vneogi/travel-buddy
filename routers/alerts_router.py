"""SPEC-29: Trip context alerts endpoint.

GET /api/v1/trip/{trip_id}/alerts

Requirements:
- Authenticated, trip-ownership enforced.
- No LLM, RAG, or state machine calls.
- No reroute quota consumption.
- No TripState mutation.
- Missing key: 200 unconfigured.
- Provider failure: 503.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from config.regions import REGIONS
from models.alerts import TripAlertsResponse
from security import get_current_user_id, require_trip_owner
from services.alert_evaluator import evaluate_alerts
from services.db_provider import db_service
from services.weather_provider import WeatherProvider, WeatherProviderError

router = APIRouter(prefix="/api/v1")

# Singleton provider (uses settings.openweather_api_key)
_weather_provider = WeatherProvider()


def get_weather_provider() -> WeatherProvider:
    return _weather_provider


@router.get("/trip/{trip_id}/alerts", response_model=TripAlertsResponse)
async def get_trip_alerts(
    trip_id: str,
    user_id: str = Depends(get_current_user_id),
    provider: WeatherProvider = Depends(get_weather_provider),
):
    """Get context alerts for a trip. Never mutates state or calls LLM."""
    trip = require_trip_owner(db_service.get_trip(trip_id), user_id)

    if not provider.is_configured:
        return TripAlertsResponse(
            trip_id=trip_id,
            status="unconfigured",
            alerts=[],
            refreshed_at=datetime.now(tz=timezone.utc),
        )

    # Determine coordinates: first upcoming node with coords, else region center
    lat, lng = None, None
    location_basis = "trip_region"

    for node in trip.nodes:
        if node.lat is not None and node.lng is not None:
            lat, lng = node.lat, node.lng
            location_basis = "node_coordinates"
            break

    if lat is None:
        region = REGIONS.get(trip.geo_region)
        if region:
            lat, lng = region.default_lat, region.default_lng
        else:
            lat, lng = 25.2048, 55.2708  # Dubai fallback

    try:
        blocks, source_updated_at = await provider.get_forecast(lat, lng)
    except WeatherProviderError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "weather_provider_unavailable", "message": str(e)},
        )

    now = datetime.now(tz=timezone.utc)
    alerts = evaluate_alerts(
        trip=trip,
        forecast_blocks=blocks,
        source_updated_at=source_updated_at,
        now=now,
        location_basis=location_basis,
    )

    # Filter expired
    alerts = [a for a in alerts if a.expires_at > now]

    return TripAlertsResponse(
        trip_id=trip_id,
        status="available",
        alerts=alerts,
        refreshed_at=now,
    )
