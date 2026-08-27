"""SPEC-29: Real weather provider (OpenWeather).

Fetches forecast data from OpenWeather API. Never invents data.
Returns typed forecast blocks for the evaluator.
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from config.settings import settings


class WeatherProviderError(Exception):
    """Raised when the weather provider is unavailable or fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ForecastBlock:
    """A single 3-hour forecast block from OpenWeather."""

    def __init__(
        self,
        dt: datetime,
        temp_c: float,
        feels_like_c: float,
        humidity: int,
        condition_code: int,
        condition_main: str,
        rain_probability: float,
        wind_speed_kmh: float,
    ):
        self.dt = dt
        self.temp_c = temp_c
        self.feels_like_c = feels_like_c
        self.humidity = humidity
        self.condition_code = condition_code
        self.condition_main = condition_main
        self.rain_probability = rain_probability
        self.wind_speed_kmh = wind_speed_kmh


class WeatherProvider:
    """OpenWeather forecast provider with 10-minute cache."""

    BASE_URL = "https://api.openweathermap.org/data/2.5"
    CACHE_TTL = 600  # 10 minutes

    def __init__(
        self,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_key = api_key or settings.openweather_api_key
        self._http_client = http_client
        self._cache: Dict[str, Tuple[List[ForecastBlock], datetime, float]] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def get_forecast(self, lat: float, lng: float) -> Tuple[List[ForecastBlock], datetime]:
        """Fetch forecast blocks for a location.

        Returns (blocks, source_updated_at).
        Raises WeatherProviderError on failure.
        """
        if not self.is_configured:
            return [], datetime.now(tz=timezone.utc)

        cache_key = f"{lat:.4f}_{lng:.4f}"
        if cache_key in self._cache:
            blocks, updated_at, cached_at = self._cache[cache_key]
            if time.time() - cached_at < self.CACHE_TTL:
                return blocks, updated_at

        params = {
            "lat": lat,
            "lon": lng,
            "appid": self.api_key,
            "units": "metric",
        }

        try:
            if self._http_client:
                client = self._http_client
                response = await client.get(f"{self.BASE_URL}/forecast", params=params)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.BASE_URL}/forecast", params=params)

            if response.status_code != 200:
                raise WeatherProviderError(
                    f"OpenWeather returned {response.status_code}",
                    status_code=response.status_code,
                )
            try:
                raw = response.json()
            except (ValueError, TypeError) as exc:
                raise WeatherProviderError("Malformed JSON from weather provider") from exc
        except WeatherProviderError:
            raise
        except httpx.TimeoutException:
            raise WeatherProviderError("OpenWeather request timed out")
        except httpx.HTTPError as e:
            raise WeatherProviderError(f"OpenWeather HTTP error: {e}")

        blocks: List[ForecastBlock] = []
        raw_list = raw.get("list")
        if not isinstance(raw_list, list):
            raise WeatherProviderError("Malformed forecast response: missing list field")
        for item in raw_list:
            dt = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
            blocks.append(
                ForecastBlock(
                    dt=dt,
                    temp_c=item["main"]["temp"],
                    feels_like_c=item["main"]["feels_like"],
                    humidity=item["main"]["humidity"],
                    condition_code=item["weather"][0]["id"],
                    condition_main=item["weather"][0]["main"],
                    rain_probability=max(0.0, min(1.0, float(item.get("pop", 0.0)))),
                    wind_speed_kmh=item["wind"]["speed"] * 3.6,
                )
            )

        source_updated_at = datetime.now(tz=timezone.utc)
        self._cache[cache_key] = (blocks, source_updated_at, time.time())
        return blocks, source_updated_at
