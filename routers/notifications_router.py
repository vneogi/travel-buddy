"""SPEC-35 Phase A: proactive departure notification endpoint.

GET /api/v1/trip/{trip_id}/notifications
- Owner-scoped, read-only.
- Never mutates trip state, consumes quota, calls LLM, or emits events.
- Provider failure is partial, not endpoint failure.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from models.notifications import TripNotificationsResponse
from security import get_current_user_id, require_trip_owner
from services.departure_evaluator import evaluate_departure
from services.db_provider import db_service
from services.route_provider import (
    GoogleMapsRouteProvider,
    RouteProvider,
)
from services.weather_provider import WeatherProvider

router = APIRouter(prefix="/api/v1")

_weather_provider = WeatherProvider()
_route_provider: RouteProvider = GoogleMapsRouteProvider()


def get_route_provider() -> RouteProvider:
    """Dependency for test injection."""
    return _route_provider


def get_weather_provider() -> WeatherProvider:
    """Dependency for test injection."""
    return _weather_provider


@router.get(
    "/trip/{trip_id}/notifications",
    response_model=TripNotificationsResponse,
)
async def get_trip_notifications(
    trip_id: str,
    user_id: str = Depends(get_current_user_id),
    route_prov: RouteProvider = Depends(get_route_provider),
    weather_prov: WeatherProvider = Depends(get_weather_provider),
):
    """Return proactive notification candidates for the trip owner."""
    # Trip storage failure -> 503
    try:
        trip = db_service.get_trip(trip_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Trip storage unavailable: {exc}",
        ) from exc

    require_trip_owner(trip, user_id)

    now = datetime.now(tz=timezone.utc)
    notifications = []
    response_status = "available"

    candidate, error = await evaluate_departure(
        trip=trip,
        now=now,
        route_provider=route_prov,
        weather_provider=weather_prov,
    )

    if candidate is not None:
        notifications.append(candidate)
    elif error and error.startswith("route_unavailable"):
        response_status = "partial"

    return TripNotificationsResponse(
        trip_id=trip_id,
        refreshed_at=now,
        status=response_status,
        notifications=notifications,
    )
