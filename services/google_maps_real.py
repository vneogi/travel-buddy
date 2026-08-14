"""Travel Buddy MVP - Real Google Maps & Places Service

Production implementation replacing the mock maps_service.py.
Integrates:
  - Distance Matrix API: Real transit times with traffic
  - Places API (New): Venue details, open_now status, ratings
  - Geocoding: Address to coordinates
  - Directions: Turn-by-turn for deep transit estimation

Requires:
  pip install googlemaps
  Environment var: TB_GOOGLE_MAPS_API_KEY

Pricing (pay-per-use):
  - Distance Matrix: $5 per 1000 elements
  - Places Details: $17 per 1000 calls
  - Places Nearby: $32 per 1000 calls
  Strategy: Cache aggressively, batch when possible.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx

from config.settings import settings


class GoogleMapsService:
    """Real Google Maps integration for transit and venue validation."""

    BASE_URL = "https://maps.googleapis.com/maps/api"
    PLACES_URL = "https://places.googleapis.com/v1/places"

    def __init__(self):
        self.api_key = settings.google_maps_api_key
        self._cache: Dict[str, Tuple[Dict, float]] = {}
        self._cache_ttl = 300  # 5 min cache for transit
        self._places_cache_ttl = 3600  # 1 hour for place details

    # =========================================================================
    # Distance Matrix API
    # =========================================================================

    async def get_transit_time(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        mode: str = "driving",
        departure_time: Optional[datetime] = None,
    ) -> Dict:
        """Get real transit time between two points.

        Returns:
        {
            "distance_km": float,
            "duration_minutes": int,
            "duration_in_traffic_minutes": int,  # Only for driving
            "mode": str,
            "traffic_condition": str,
        }
        """
        cache_key = f"transit_{origin_lat}_{origin_lng}_{dest_lat}_{dest_lng}_{mode}"
        cached = self._get_cached(cache_key, self._cache_ttl)
        if cached:
            return cached

        params = {
            "origins": f"{origin_lat},{origin_lng}",
            "destinations": f"{dest_lat},{dest_lng}",
            "mode": mode,
            "key": self.api_key,
            "units": "metric",
        }

        # Add departure_time for traffic-aware routing
        if mode == "driving":
            dep_time = departure_time or datetime.now()
            params["departure_time"] = int(dep_time.timestamp())
            params["traffic_model"] = "best_guess"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/distancematrix/json", params=params
            )
            response.raise_for_status()
            data = response.json()

        if data["status"] != "OK":
            raise ValueError(f"Distance Matrix API error: {data['status']}")

        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            raise ValueError(f"Route not found: {element['status']}")

        distance_km = element["distance"]["value"] / 1000
        duration_min = element["duration"]["value"] / 60

        # Traffic-aware duration (driving only)
        traffic_min = duration_min
        if "duration_in_traffic" in element:
            traffic_min = element["duration_in_traffic"]["value"] / 60

        # Classify traffic condition
        ratio = traffic_min / duration_min if duration_min > 0 else 1
        if ratio > 1.4:
            traffic_condition = "heavy"
        elif ratio > 1.15:
            traffic_condition = "moderate"
        else:
            traffic_condition = "light"

        result = {
            "distance_km": round(distance_km, 2),
            "duration_minutes": int(duration_min),
            "duration_in_traffic_minutes": int(traffic_min),
            "mode": mode,
            "traffic_condition": traffic_condition,
        }

        self._cache[cache_key] = (result, time.time())
        return result

    # =========================================================================
    # Places API (New)
    # =========================================================================

    async def search_nearby_places(
        self,
        lat: float,
        lng: float,
        radius_meters: int = 5000,
        place_type: str = "restaurant",
        keyword: Optional[str] = None,
        open_now: bool = True,
    ) -> List[Dict]:
        """Search for places near a location.

        Uses Places API (New) for better results and field masking.
        """
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,"
                "places.location,places.rating,places.userRatingCount,"
                "places.currentOpeningHours,places.types,places.id"
            ),
        }

        body = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": radius_meters,
                }
            },
            "includedTypes": [place_type],
            "maxResultCount": 10,
        }

        if keyword:
            body["textQuery"] = keyword

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.PLACES_URL}:searchNearby",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        places = []
        for place in data.get("places", []):
            is_open = True
            if "currentOpeningHours" in place:
                is_open = place["currentOpeningHours"].get("openNow", True)

            if open_now and not is_open:
                continue

            places.append({
                "place_id": place.get("id"),
                "name": place.get("displayName", {}).get("text", ""),
                "address": place.get("formattedAddress", ""),
                "lat": place.get("location", {}).get("latitude"),
                "lng": place.get("location", {}).get("longitude"),
                "rating": place.get("rating"),
                "review_count": place.get("userRatingCount"),
                "is_open_now": is_open,
                "types": place.get("types", []),
            })

        return places

    async def get_place_details(self, place_id: str) -> Dict:
        """Get detailed info for a specific place."""
        cache_key = f"place_{place_id}"
        cached = self._get_cached(cache_key, self._places_cache_ttl)
        if cached:
            return cached

        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "displayName,formattedAddress,location,rating,"
                "userRatingCount,currentOpeningHours,regularOpeningHours,"
                "priceLevel,websiteUri,nationalPhoneNumber,"
                "editorialSummary,types"
            ),
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.PLACES_URL}/{place_id}",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        result = {
            "place_id": place_id,
            "name": data.get("displayName", {}).get("text", ""),
            "address": data.get("formattedAddress", ""),
            "lat": data.get("location", {}).get("latitude"),
            "lng": data.get("location", {}).get("longitude"),
            "rating": data.get("rating"),
            "review_count": data.get("userRatingCount"),
            "price_level": data.get("priceLevel"),
            "website": data.get("websiteUri"),
            "phone": data.get("nationalPhoneNumber"),
            "summary": data.get("editorialSummary", {}).get("text"),
            "is_open_now": data.get("currentOpeningHours", {}).get("openNow"),
            "hours": data.get("regularOpeningHours", {}).get("weekdayDescriptions"),
        }

        self._cache[cache_key] = (result, time.time())
        return result

    async def validate_venues_open(
        self, venues: List[Dict]
    ) -> List[Dict]:
        """Cross-reference venues with Places API for open_now status.

        This is Step 3 from BRD Section 3.3.
        """
        validated = []
        for venue in venues:
            # If we have a place_id, verify with API
            if venue.get("place_id"):
                try:
                    details = await self.get_place_details(venue["place_id"])
                    if details.get("is_open_now", True):
                        venue["verified_open"] = True
                        venue["rating"] = details.get("rating")
                        validated.append(venue)
                except Exception:
                    # If API fails, include venue optimistically
                    validated.append(venue)
            else:
                # No place_id -- use time-based heuristic from mock
                validated.append(venue)

        return validated

    # =========================================================================
    # Utility
    # =========================================================================

    def _get_cached(self, key: str, ttl: float) -> Optional[Dict]:
        """Check cache for a valid entry."""
        if key in self._cache:
            data, cached_at = self._cache[key]
            if time.time() - cached_at < ttl:
                return data
        return None

    async def batch_transit_times(
        self,
        origin: Tuple[float, float],
        destinations: List[Tuple[float, float]],
        mode: str = "driving",
    ) -> List[Dict]:
        """Get transit times to multiple destinations in one API call.

        More efficient than individual calls (1 API call vs N).
        """
        dest_str = "|".join(f"{lat},{lng}" for lat, lng in destinations)

        params = {
            "origins": f"{origin[0]},{origin[1]}",
            "destinations": dest_str,
            "mode": mode,
            "key": self.api_key,
            "units": "metric",
            "departure_time": "now",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/distancematrix/json", params=params
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for element in data["rows"][0]["elements"]:
            if element["status"] == "OK":
                results.append({
                    "distance_km": element["distance"]["value"] / 1000,
                    "duration_minutes": element["duration"]["value"] / 60,
                    "status": "ok",
                })
            else:
                results.append({"status": "not_found"})

        return results


# Singleton instance
google_maps_real = GoogleMapsService()
