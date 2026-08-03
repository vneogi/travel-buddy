"""Travel Buddy MVP - Maps & Places Service

Mock implementation of Google Maps Distance Matrix and Places API.
Returns realistic synthetic data for Dubai venues.
In production, replace with actual Google API calls.
"""

import math
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class MapsService:
    """Handles transit time calculations and venue validation."""

    # Dubai landmark coordinates for reference
    DUBAI_LANDMARKS = {
        "burj_khalifa": (25.1972, 55.2744),
        "dubai_mall": (25.1985, 55.2796),
        "palm_jumeirah": (25.1124, 55.1390),
        "dubai_marina": (25.0805, 55.1403),
        "difc": (25.2100, 55.2800),
        "al_quoz": (25.1500, 55.2300),
        "jumeirah": (25.2100, 55.2500),
        "deira": (25.2700, 55.3100),
        "business_bay": (25.1860, 55.2650),
        "jbr": (25.0780, 55.1340),
    }

    def calculate_distance_km(
        self, lat1: float, lng1: float, lat2: float, lng2: float
    ) -> float:
        """Calculate distance between two points using Haversine formula."""
        R = 6371  # Earth's radius in km

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def get_transit_time(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        mode: str = "driving",
    ) -> Dict:
        """Get estimated transit time between two points.

        Mock implementation: estimates based on distance with Dubai-specific
        traffic multipliers.
        """
        distance_km = self.calculate_distance_km(
            origin_lat, origin_lng, dest_lat, dest_lng
        )

        # Dubai traffic speed estimates (km/h)
        speed_map = {
            "driving": 35,  # Average with traffic
            "taxi": 35,
            "metro": 45,
            "walking": 5,
        }

        # Time-of-day traffic multiplier
        hour = datetime.now().hour
        if 7 <= hour <= 9 or 17 <= hour <= 19:
            traffic_multiplier = 1.5  # Rush hour
        elif 12 <= hour <= 14:
            traffic_multiplier = 1.2  # Lunch traffic
        else:
            traffic_multiplier = 1.0

        base_speed = speed_map.get(mode, 35)
        minutes = (distance_km / base_speed) * 60 * traffic_multiplier

        # Add some realistic variance
        variance = random.uniform(0.9, 1.15)
        minutes = int(minutes * variance)

        return {
            "distance_km": round(distance_km, 2),
            "duration_minutes": max(5, minutes),  # Minimum 5 min
            "mode": mode,
            "traffic_condition": (
                "heavy" if traffic_multiplier > 1.3 else
                "moderate" if traffic_multiplier > 1.0 else
                "light"
            ),
        }

    def check_venue_open(
        self, venue_hours: str, check_time: Optional[datetime] = None
    ) -> bool:
        """Check if a venue is currently open based on its hours string.

        Hours format: "HH:MM-HH:MM" (e.g., "09:00-23:00")
        """
        if not check_time:
            check_time = datetime.now()

        try:
            open_str, close_str = venue_hours.split("-")
            open_hour, open_min = map(int, open_str.split(":"))
            close_hour, close_min = map(int, close_str.split(":"))

            current_minutes = check_time.hour * 60 + check_time.minute
            open_minutes = open_hour * 60 + open_min
            close_minutes = close_hour * 60 + close_min

            # Handle venues that close after midnight
            if close_minutes < open_minutes:
                return current_minutes >= open_minutes or current_minutes <= close_minutes
            else:
                return open_minutes <= current_minutes <= close_minutes
        except (ValueError, AttributeError):
            return True  # Default to open if can't parse

    def validate_venues(
        self,
        venues: List[Dict],
        user_lat: float,
        user_lng: float,
        max_transit_minutes: int = 30,
    ) -> List[Dict]:
        """Validate venues: check open status and filter by transit time.

        This is Step 3 from the BRD hybrid retrieval:
        Cross-reference top results with Places API to ensure open_now.
        """
        validated = []

        for venue in venues:
            # Check if open
            is_open = self.check_venue_open(
                venue.get("opening_hours", "09:00-23:00")
            )

            if not is_open:
                continue

            # Calculate transit time
            transit = self.get_transit_time(
                user_lat, user_lng,
                venue.get("lat", 25.1972),
                venue.get("lng", 55.2744)
            )

            if transit["duration_minutes"] <= max_transit_minutes:
                venue["transit_info"] = transit
                venue["is_open_now"] = True
                validated.append(venue)

        return validated

    def get_nearby_landmarks(
        self, lat: float, lng: float, radius_km: float = 2.0
    ) -> List[Tuple[str, float]]:
        """Get nearby Dubai landmarks for context."""
        nearby = []
        for name, (l_lat, l_lng) in self.DUBAI_LANDMARKS.items():
            dist = self.calculate_distance_km(lat, lng, l_lat, l_lng)
            if dist <= radius_km:
                nearby.append((name.replace("_", " ").title(), round(dist, 2)))

        return sorted(nearby, key=lambda x: x[1])


# Singleton instance
maps_service = MapsService()
