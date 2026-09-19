"""SPEC-41 configured-env guards.

Two bugs fixed:
1. WeatherProvider(api_key="") must stay unconfigured even when
   settings.openweather_api_key is set.
2. swap_activity must never call generate_itinerary_response /
   generate_info_response when LLM keys exist.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch as mock_patch

import pytest

from services.weather_provider import WeatherProvider


# ---------------------------------------------------------------------------
# 1. WeatherProvider empty-string guard
# ---------------------------------------------------------------------------


class TestWeatherProviderGuard:
    def test_explicit_empty_string_stays_unconfigured(self, monkeypatch):
        """WeatherProvider(api_key='') must NOT fall through to settings."""
        monkeypatch.setattr(
            "services.weather_provider.settings.openweather_api_key",
            "real-key-from-env",
        )
        provider = WeatherProvider(api_key="")
        assert provider.api_key == ""
        assert provider.is_configured is False

    def test_none_falls_through_to_settings(self, monkeypatch):
        """WeatherProvider(api_key=None) should use settings."""
        monkeypatch.setattr(
            "services.weather_provider.settings.openweather_api_key",
            "real-key-from-env",
        )
        provider = WeatherProvider(api_key=None)
        assert provider.api_key == "real-key-from-env"
        assert provider.is_configured is True

    def test_default_none_falls_through(self, monkeypatch):
        """WeatherProvider() should use settings."""
        monkeypatch.setattr(
            "services.weather_provider.settings.openweather_api_key",
            "real-key-from-env",
        )
        provider = WeatherProvider()
        assert provider.api_key == "real-key-from-env"
        assert provider.is_configured is True

    def test_explicit_key_used_directly(self):
        """WeatherProvider(api_key='my-key') uses that key."""
        provider = WeatherProvider(api_key="my-key")
        assert provider.api_key == "my-key"
        assert provider.is_configured is True

    def test_sabotage_or_fallthrough_fails(self, monkeypatch):
        """Sabotage: reverting to `api_key or settings...` would make
        empty string pick up the settings key."""
        monkeypatch.setattr(
            "services.weather_provider.settings.openweather_api_key",
            "real-key-from-env",
        )
        provider = WeatherProvider(api_key="")
        # With old code (api_key or settings), this would be "real-key-from-env"
        assert provider.api_key != "real-key-from-env"


# ---------------------------------------------------------------------------
# 2. swap_activity never calls LLM
# ---------------------------------------------------------------------------


class TestSwapActivityNoLLM:
    def test_swap_does_not_call_llm_when_keys_exist(self, client, monkeypatch):
        """swap_activity must return a deterministic response, never
        calling generate_itinerary_response or generate_info_response."""
        from tests.conftest import auth

        # Set LLM keys so the LLM path would fire for non-swap events
        from config.settings import settings as _settings

        monkeypatch.setattr(_settings, "litellm_api_key", "fake-llm-key")
        monkeypatch.setattr(_settings, "gemini_api_key", "fake-gemini-key")

        # Bomb: if LLM is called, the test fails
        def _llm_bomb(*a, **kw):
            raise AssertionError("LLM must not be called for swap_activity")

        monkeypatch.setattr(
            "services.llm_service.llm_service.generate_itinerary_response",
            AsyncMock(side_effect=_llm_bomb),
        )
        monkeypatch.setattr(
            "services.llm_service.llm_service.generate_info_response",
            AsyncMock(side_effect=_llm_bomb),
        )

        # Create trip
        created = client.post(
            "/api/v1/trip/create",
            headers=auth("swap-no-llm-user"),
            json={
                "start_date": "2026-10-05T09:00:00",
                "geo_region": "vang_vieng_laos",
            },
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        # Find first unlocked activity
        fetched = client.get(f"/api/v1/trip/{trip_id}", headers=auth("swap-no-llm-user"))
        assert fetched.status_code == 200
        nodes = fetched.json()["nodes"]
        target = next(
            (
                n
                for n in nodes
                if not n.get("is_locked") and n.get("node_kind", "activity") == "activity"
            ),
            None,
        )
        assert target is not None, "Need an unlocked activity to swap"

        # Swap -- must not trigger LLM
        swap_resp = client.post(
            "/api/v1/trip/event",
            headers=auth("swap-no-llm-user"),
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Something different",
                "target_node_id": target["node_id"],
            },
        )
        assert swap_resp.status_code == 200
        body = swap_resp.json()
        # Response must be the canned swap text, not an LLM generation
        response_text = body.get("message", "")
        assert "swapped" in response_text.lower() or "couldn't find" in response_text.lower(), (
            f"Expected deterministic swap response, got: {response_text}"
        )

    def test_swap_response_names_venue_when_successful(self, client, monkeypatch):
        """A successful swap should name the replacement venue."""
        from tests.conftest import auth
        from services.database_service import db_service
        from models.schemas import VenueRAG

        # Inject a deterministic replacement
        replacement = VenueRAG(
            venue_id="swap-guard-venue-001",
            name="Guard Test Cafe",
            description="Test venue",
            micro_location="Test location",
            lat=18.935,
            lng=102.465,
            vibe_tags=["test"],
            geo_region="vang_vieng_laos",
            typical_dwell_minutes=60,
        )
        db_service.add_venue(replacement)

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("swap-named-user"),
            json={
                "start_date": "2026-10-05T09:00:00",
                "geo_region": "vang_vieng_laos",
            },
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        fetched = client.get(f"/api/v1/trip/{trip_id}", headers=auth("swap-named-user"))
        nodes = fetched.json()["nodes"]
        target = next(
            n
            for n in nodes
            if not n.get("is_locked") and n.get("node_kind", "activity") == "activity"
        )

        swap_resp = client.post(
            "/api/v1/trip/event",
            headers=auth("swap-named-user"),
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Something different",
                "target_node_id": target["node_id"],
                "preferences": {
                    "replacement_venue_id": "swap-guard-venue-001",
                },
            },
        )
        assert swap_resp.status_code == 200
        response_text = swap_resp.json().get("message", "")
        assert "Guard Test Cafe" in response_text, (
            f"Expected venue name in response, got: {response_text}"
        )


# ---------------------------------------------------------------------------
# 3. Refused swap keeps honest refusal, never says "Swapped..."
# ---------------------------------------------------------------------------


class TestSwapNoCandidateCopy:
    def test_refused_swap_shows_refusal_not_swapped(self, client, monkeypatch):
        """When swap finds no candidates, the response must be the honest
        refusal ('couldn\'t find'), never 'Swapped to ...' or 'Activity swapped.'"""
        from tests.conftest import auth

        created = client.post(
            "/api/v1/trip/create",
            headers=auth("no-cand-user"),
            json={
                "start_date": "2026-10-05T09:00:00",
                "geo_region": "vang_vieng_laos",
            },
        )
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        fetched = client.get(f"/api/v1/trip/{trip_id}", headers=auth("no-cand-user"))
        nodes = fetched.json()["nodes"]
        target = next(
            (
                n
                for n in nodes
                if not n.get("is_locked") and n.get("node_kind", "activity") == "activity"
            ),
            None,
        )
        assert target is not None

        # Patch venue search to return nothing -- forces no_candidates
        monkeypatch.setattr(
            "services.database_service.db_service.hybrid_venue_search",
            lambda **kw: [],
        )

        swap_resp = client.post(
            "/api/v1/trip/event",
            headers=auth("no-cand-user"),
            json={
                "trip_id": trip_id,
                "event_type": "swap_activity",
                "message": "Something completely different",
                "target_node_id": target["node_id"],
            },
        )
        assert swap_resp.status_code == 200
        msg = swap_resp.json().get("message", "")

        # Must be the honest refusal
        assert "couldn't find" in msg.lower(), f"Expected honest refusal, got: {msg}"
        # Must NOT say "Swapped"
        assert "swapped" not in msg.lower(), f"Refused swap must not say 'Swapped', got: {msg}"
