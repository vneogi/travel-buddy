"""SPEC-35: Injectable route-provider interface and cached adapter.

The interface is protocol-based so tests can substitute a stub without
touching provider code. The Google Maps adapter delegates to the existing
GoogleMapsService with a five-minute coordinate-rounded cache.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple


class RouteProviderError(Exception):
    """Raised when the route provider is unavailable or fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RouteResult:
    """Provider-backed route observation."""

    normal_duration_minutes: Optional[int]
    traffic_duration_minutes: int
    mode: str
    observed_at: datetime
    source: str


class RouteProvider(ABC):
    """Injectable interface for route duration lookups."""

    @abstractmethod
    async def get_driving_duration(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        departure_time: Optional[datetime] = None,
    ) -> RouteResult:
        """Return a departure-time-aware driving estimate.

        Raises RouteProviderError when the provider is unavailable.
        """


def _round_coord(v: float) -> float:
    """Round to 3 decimals (~100 m) for cache keying."""
    return round(v, 3)


def _time_bucket(dt: Optional[datetime]) -> str:
    """Round departure time to a 10-minute bucket for cache keying."""
    if dt is None:
        return "none"
    return dt.strftime("%Y%m%d%H") + str(dt.minute // 10)


class GoogleMapsRouteProvider(RouteProvider):
    """Adapter over GoogleMapsService with five-minute cache."""

    CACHE_TTL = 300  # 5 minutes

    def __init__(self, maps_service=None):
        self._maps = maps_service
        self._cache: Dict[str, Tuple[RouteResult, float]] = {}

    @property
    def is_configured(self) -> bool:
        return self._maps is not None and getattr(self._maps, "api_key", None)

    async def get_driving_duration(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        departure_time: Optional[datetime] = None,
    ) -> RouteResult:
        if not self.is_configured:
            raise RouteProviderError("Google Maps API key not configured")

        cache_key = (
            f"{_round_coord(origin_lat)},{_round_coord(origin_lng)}"
            f"->{_round_coord(dest_lat)},{_round_coord(dest_lng)}"
            f":{_time_bucket(departure_time)}"
        )

        now_mono = time.time()
        if cache_key in self._cache:
            cached_result, cached_at = self._cache[cache_key]
            if now_mono - cached_at < self.CACHE_TTL:
                return cached_result

        try:
            raw = await self._maps.get_transit_time(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                dest_lat=dest_lat,
                dest_lng=dest_lng,
                mode="driving",
                departure_time=departure_time,
            )
        except Exception as exc:
            raise RouteProviderError(f"Google Maps request failed: {exc}") from exc

        from datetime import timezone

        result = RouteResult(
            normal_duration_minutes=raw.get("duration_minutes"),
            traffic_duration_minutes=raw.get("duration_in_traffic_minutes")
            or raw.get("duration_minutes", 0),
            mode="driving",
            observed_at=datetime.now(tz=timezone.utc),
            source="google_maps",
        )
        self._cache[cache_key] = (result, now_mono)
        return result
