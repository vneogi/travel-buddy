"""Travel Buddy MVP - Weather Service

⚠️  STATUS: SCAFFOLDED — NOT WIRED INTO THE REQUEST PATH.
    weather_alert events route to the LLM but never call this service.
    Real weather fetching + auto-swap is a future milestone.
    Requires: TB_OPENWEATHER_API_KEY in .env.

Integrates with OpenWeatherMap API for Dubai-specific weather data.
Triggers proactive itinerary adjustments when conditions change:
  - Extreme heat (>45C) -> suggest indoor alternatives
  - Rain/storms -> swap outdoor activities
  - Sandstorms -> cancel desert activities
  - Humidity >80% -> prefer air-conditioned venues

Requires:
  Environment var: TB_OPENWEATHER_API_KEY
  Free tier: 60 calls/min, current weather + 5-day forecast
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx

from config.settings import settings


# Dubai-specific weather thresholds
class WeatherThresholds:
    EXTREME_HEAT_C = 45
    HIGH_HEAT_C = 40
    RAIN_CODES = {200, 201, 202, 210, 211, 212, 221, 230, 231, 232,
                  300, 301, 302, 310, 311, 312, 313, 314, 321,
                  500, 501, 502, 503, 504, 511, 520, 521, 522, 531}
    STORM_CODES = {200, 201, 202, 210, 211, 212, 221, 230, 231, 232, 771, 781}
    SAND_CODES = {731, 751, 761, 762}  # Dust/sand
    HIGH_HUMIDITY_PERCENT = 80


class WeatherAlert:
    """A weather condition that should trigger itinerary adjustment."""

    def __init__(
        self,
        alert_type: str,
        severity: str,  # "warning", "advisory", "info"
        message: str,
        swap_to_indoor: bool = False,
        cancel_outdoor: bool = False,
    ):
        self.alert_type = alert_type
        self.severity = severity
        self.message = message
        self.swap_to_indoor = swap_to_indoor
        self.cancel_outdoor = cancel_outdoor
        self.timestamp = datetime.utcnow()


class WeatherService:
    """OpenWeatherMap integration for proactive weather triggers."""

    BASE_URL = "https://api.openweathermap.org/data/2.5"

    # Dubai coordinates
    DUBAI_LAT = 25.2048
    DUBAI_LNG = 55.2708

    def __init__(self):
        self.api_key = settings.openweather_api_key  # TB_OPENWEATHER_API_KEY
        self._cache: Dict[str, Tuple[Dict, float]] = {}  # Simple TTL cache
        self._cache_ttl = 600  # 10 minutes

    async def get_current_weather(
        self, lat: float = None, lng: float = None
    ) -> Dict:
        """Get current weather conditions for a location.

        Returns standardized weather dict:
        {
            "temp_c": float,
            "feels_like_c": float,
            "humidity": int,
            "condition": str,
            "condition_code": int,
            "wind_speed_kmh": float,
            "visibility_km": float,
            "description": str,
            "is_daytime": bool,
            "uv_index": Optional[float],
        }
        """
        lat = lat or self.DUBAI_LAT
        lng = lng or self.DUBAI_LNG

        # Check cache
        cache_key = f"current_{lat}_{lng}"
        if cache_key in self._cache:
            data, cached_at = self._cache[cache_key]
            if time.time() - cached_at < self._cache_ttl:
                return data

        # API call
        params = {
            "lat": lat,
            "lon": lng,
            "appid": self.api_key,
            "units": "metric",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/weather", params=params
            )
            response.raise_for_status()
            raw = response.json()

        weather = {
            "temp_c": raw["main"]["temp"],
            "feels_like_c": raw["main"]["feels_like"],
            "humidity": raw["main"]["humidity"],
            "condition": raw["weather"][0]["main"],
            "condition_code": raw["weather"][0]["id"],
            "wind_speed_kmh": raw["wind"]["speed"] * 3.6,
            "visibility_km": raw.get("visibility", 10000) / 1000,
            "description": raw["weather"][0]["description"],
            "is_daytime": (
                raw["sys"]["sunrise"] < time.time() < raw["sys"]["sunset"]
            ),
            "uv_index": None,  # Requires separate UV API call
        }

        # Cache result
        self._cache[cache_key] = (weather, time.time())
        return weather

    async def get_forecast_hours(
        self, hours_ahead: int = 6, lat: float = None, lng: float = None
    ) -> List[Dict]:
        """Get hourly forecast for the next N hours.

        Useful for planning: will it rain during the traveler's
        afternoon outdoor activity?
        """
        lat = lat or self.DUBAI_LAT
        lng = lng or self.DUBAI_LNG

        params = {
            "lat": lat,
            "lon": lng,
            "appid": self.api_key,
            "units": "metric",
            # cnt counts 3-hour blocks; to cover N hours we need ceil(N/3)
            "cnt": min((hours_ahead + 2) // 3, 40),
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/forecast", params=params
            )
            response.raise_for_status()
            raw = response.json()

        forecasts = []
        for item in raw.get("list", [])  # already limited by cnt param; return all fetched blocks:
            forecasts.append({
                "datetime": item["dt_txt"],
                "temp_c": item["main"]["temp"],
                "humidity": item["main"]["humidity"],
                "condition": item["weather"][0]["main"],
                "condition_code": item["weather"][0]["id"],
                "description": item["weather"][0]["description"],
                "wind_speed_kmh": item["wind"]["speed"] * 3.6,
            })

        return forecasts

    def evaluate_alerts(self, weather: Dict) -> List[WeatherAlert]:
        """Evaluate current weather against thresholds.

        Returns list of active alerts that should trigger itinerary changes.
        """
        alerts = []
        code = weather.get("condition_code", 800)
        temp = weather.get("temp_c", 30)
        humidity = weather.get("humidity", 50)

        # Extreme heat
        if temp >= WeatherThresholds.EXTREME_HEAT_C:
            alerts.append(WeatherAlert(
                alert_type="extreme_heat",
                severity="warning",
                message=(
                    f"Temperature is {temp}°C. Outdoor activities are dangerous. "
                    "Strongly recommend indoor air-conditioned alternatives."
                ),
                swap_to_indoor=True,
                cancel_outdoor=True,
            ))
        elif temp >= WeatherThresholds.HIGH_HEAT_C:
            alerts.append(WeatherAlert(
                alert_type="high_heat",
                severity="advisory",
                message=(
                    f"Temperature is {temp}°C with {humidity}% humidity. "
                    "Consider shorter outdoor activities or shaded venues."
                ),
                swap_to_indoor=False,
            ))

        # Rain/storms
        if code in WeatherThresholds.STORM_CODES:
            alerts.append(WeatherAlert(
                alert_type="storm",
                severity="warning",
                message="Thunderstorm conditions. All outdoor activities should move indoors.",
                swap_to_indoor=True,
                cancel_outdoor=True,
            ))
        elif code in WeatherThresholds.RAIN_CODES:
            alerts.append(WeatherAlert(
                alert_type="rain",
                severity="advisory",
                message="Rain expected. Outdoor activities may be affected.",
                swap_to_indoor=True,
            ))

        # Sandstorms
        if code in WeatherThresholds.SAND_CODES:
            alerts.append(WeatherAlert(
                alert_type="sandstorm",
                severity="warning",
                message="Dust/sand storm conditions. Avoid all outdoor activities.",
                swap_to_indoor=True,
                cancel_outdoor=True,
            ))

        # High humidity
        if humidity >= WeatherThresholds.HIGH_HUMIDITY_PERCENT and temp >= 35:
            alerts.append(WeatherAlert(
                alert_type="high_humidity",
                severity="info",
                message=(
                    f"Humidity at {humidity}% with {temp}°C. "
                    "Extended outdoor walking will be uncomfortable."
                ),
                swap_to_indoor=False,
            ))

        return alerts

    def should_trigger_swap(
        self, weather: Dict, activity_is_outdoor: bool = True
    ) -> Optional[WeatherAlert]:
        """Check if weather conditions warrant an automatic swap.

        Returns the highest-severity alert that requires action, or None.
        """
        if not activity_is_outdoor:
            return None

        alerts = self.evaluate_alerts(weather)
        # Return most severe alert that requires indoor swap
        for alert in sorted(
            alerts, key=lambda a: {"warning": 3, "advisory": 2, "info": 1}[a.severity],
            reverse=True,
        ):
            if alert.swap_to_indoor:
                return alert

        return None


# Singleton instance
weather_service = WeatherService()
