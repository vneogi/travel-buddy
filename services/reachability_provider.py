"""Optional network reachability (decision docs/decisions/NETWORK_REACHABILITY.md).

ReachabilityProvider is a swappable interface; GoogleIsochronesProvider calls
the Google Maps Platform Isochrones generate method for a walking area. It is
an enrichment over Haversine, never a replacement: callers fall back to the
Haversine estimate on any ReachabilityError.

- Off by default: get_reachability_provider() returns None unless
  TB_REACHABILITY_PROVIDER is exactly "google_isochrones" and
  TB_GOOGLE_MAPS_API_KEY is set.
- Short-TTL, bounded cache keyed on ~100 m rounded origin and minutes. A hit
  makes no HTTP call and records no spend. Failures are not cached.
- Dedicated spend circuit (SPEC-43 Gap 11 pattern), separate from the LLM
  budget. allow() is checked before any socket; record() after a successful
  parse (Preview is free; this meters volume).
- Errors are closed codes. The API key goes in a header only. Logs carry the
  closed code only: never the key, coordinates, URLs or response bodies.
"""

from __future__ import annotations

import logging
import math
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

import httpx

from monitoring.spend_circuit import SpendCircuit
from services.geo_polygon import GeoJSONError, point_in_multipolygon, polygons_from_geojson

logger = logging.getLogger("travelbuddy")

ISOCHRONES_URL = "https://isochrones.googleapis.com/v1/isochrones:generate"
FIELD_MASK = "*"
HTTP_TIMEOUT_S = 3.0
CACHE_TTL_S = 3600
CACHE_MAX_ENTRIES = 256
MAX_WALK_MINUTES = 120  # WALK max travelDuration is 7200 s
ISOCHRONE_EST_USD_PER_CALL = 0.003
PROVIDER_NAME = "google_isochrones"

ERROR_CODES = frozenset(
    {
        "not_configured",
        "invalid_input",
        "spend_capped",
        "timeout",
        "http_error",
        "parse_error",
        "origin_outside",
    }
)

# About 500 calls/day per process and 50 per identity. Not default_spend_circuit
# (that one is the LLM budget).
isochrone_spend_circuit = SpendCircuit(max_process_usd=1.50, max_identity_usd=0.15)


class ReachabilityError(Exception):
    """Closed-code provider failure; the message is the code only."""

    def __init__(self, code: str):
        if code not in ERROR_CODES:
            raise ValueError("unknown reachability error code")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class IsochroneResult:
    polygons: tuple
    minutes: int
    mode: str
    source: str
    observed_at: datetime


class ReachabilityProvider(ABC):
    """Injectable interface for walking reachability areas."""

    @abstractmethod
    async def walk_isochrone(
        self, lat: float, lng: float, minutes: int, identity: object
    ) -> IsochroneResult:
        """Return the walking area from (lat, lng). Raises ReachabilityError."""

    async def walk_isochrone_to(
        self, lat: float, lng: float, minutes: int, identity: object
    ) -> IsochroneResult:
        """Return the area from which (lat, lng) is reachable on foot.

        Concrete default so providers that only implement walk_isochrone keep
        working; they report not_configured for the reverse direction.
        """
        raise ReachabilityError("not_configured")


def _valid_input(lat, lng, minutes) -> bool:
    if isinstance(lat, bool) or isinstance(lng, bool) or isinstance(minutes, bool):
        return False
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(lat_f) and math.isfinite(lng_f)):
        return False
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0):
        return False
    return isinstance(minutes, int) and 1 <= minutes <= MAX_WALK_MINUTES


def _freeze(polygons) -> tuple:
    return tuple(tuple(tuple(tuple(pt) for pt in ring) for ring in poly) for poly in polygons)


class GoogleIsochronesProvider(ReachabilityProvider):
    """Google Isochrones (Preview) walking areas with cache and spend circuit."""

    def __init__(
        self,
        api_key: Optional[str],
        transport: Optional[httpx.AsyncBaseTransport] = None,
        spend_circuit: Optional[SpendCircuit] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._api_key = (api_key or "").strip()
        self._transport = transport
        self._circuit = spend_circuit if spend_circuit is not None else isochrone_spend_circuit
        self._clock = clock
        self._cache: "OrderedDict[str, Tuple[IsochroneResult, float]]" = OrderedDict()

    @staticmethod
    def _cache_key(lat: float, lng: float, minutes: int) -> str:
        return f"{round(lat, 3)},{round(lng, 3)}:{minutes}"

    def _cache_get(self, key: str) -> Optional[IsochroneResult]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        result, stored_at = entry
        if self._clock() - stored_at >= CACHE_TTL_S:
            self._cache.pop(key, None)
            return None
        return result

    def _cache_put(self, key: str, result: IsochroneResult) -> None:
        self._cache.pop(key, None)
        self._cache[key] = (result, self._clock())
        while len(self._cache) > CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)  # oldest insert

    def _fail(self, code: str, direction: str = "FROM") -> ReachabilityError:
        if direction == "TO":
            logger.info("reachability provider=%s direction=to outcome=%s", PROVIDER_NAME, code)
        else:
            logger.info("reachability provider=%s outcome=%s", PROVIDER_NAME, code)
        return ReachabilityError(code)

    async def walk_isochrone(
        self, lat: float, lng: float, minutes: int, identity: object
    ) -> IsochroneResult:
        return await self._walk(lat, lng, minutes, identity, "FROM")

    async def walk_isochrone_to(
        self, lat: float, lng: float, minutes: int, identity: object
    ) -> IsochroneResult:
        return await self._walk(lat, lng, minutes, identity, "TO")

    async def _walk(
        self, lat: float, lng: float, minutes: int, identity: object, direction: str
    ) -> IsochroneResult:
        if not self._api_key:
            raise self._fail("not_configured", direction)
        if not _valid_input(lat, lng, minutes):
            raise self._fail("invalid_input", direction)
        lat, lng = float(lat), float(lng)

        key = self._cache_key(lat, lng, minutes)
        if direction == "TO":
            key = f"{key}:to"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        if not self._circuit.allow(identity, ISOCHRONE_EST_USD_PER_CALL):
            raise self._fail("spend_capped", direction)

        body = {
            "location": {"latitude": lat, "longitude": lng},
            "travelDuration": f"{minutes * 60}s",
            "travelMode": "WALK",
            "travelDirection": direction,
            "routingPreference": "TRAFFIC_UNAWARE",
            "enableSmoothing": False,
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=HTTP_TIMEOUT_S
            ) as client:
                response = await client.post(ISOCHRONES_URL, json=body, headers=headers)
        except httpx.TimeoutException:
            raise self._fail("timeout", direction) from None
        except httpx.HTTPError:
            raise self._fail("http_error", direction) from None
        if not 200 <= response.status_code < 300:
            raise self._fail("http_error", direction)

        try:
            polygons = polygons_from_geojson(response.json())
        except (ValueError, GeoJSONError, KeyError, TypeError, AttributeError, IndexError):
            raise self._fail("parse_error", direction) from None
        if not polygons:
            raise self._fail("parse_error", direction)
        try:
            contains_origin = point_in_multipolygon(lng, lat, polygons)
        except (TypeError, IndexError, ZeroDivisionError):
            raise self._fail("parse_error", direction) from None
        if not contains_origin:
            raise self._fail("origin_outside", direction)

        result = IsochroneResult(
            polygons=_freeze(polygons),
            minutes=minutes,
            mode="walk",
            source="network_isochrone",
            observed_at=datetime.now(timezone.utc),
        )
        self._circuit.record(identity, ISOCHRONE_EST_USD_PER_CALL)
        self._cache_put(key, result)
        if direction == "TO":
            logger.info("reachability provider=%s direction=to outcome=ok", PROVIDER_NAME)
        else:
            logger.info("reachability provider=%s outcome=ok", PROVIDER_NAME)
        return result


_provider: Optional[GoogleIsochronesProvider] = None


def get_reachability_provider() -> Optional[ReachabilityProvider]:
    """The process singleton when enabled and keyed, else None."""
    global _provider
    from config.settings import settings

    if getattr(settings, "reachability_provider", "off") != PROVIDER_NAME:
        return None
    api_key = (settings.google_maps_api_key or "").strip()
    if not api_key:
        return None
    if _provider is None:
        _provider = GoogleIsochronesProvider(api_key)
    return _provider


def booking_return_enabled() -> bool:
    """True only when TB_REACHABILITY_BOOKING_RETURN is exactly "on".

    Callers still need get_reachability_provider() to return a provider.
    """
    from config.settings import settings

    return getattr(settings, "reachability_booking_return", "off") == "on"


def _reset_for_tests() -> None:
    global _provider
    _provider = None
    isochrone_spend_circuit.reset()
