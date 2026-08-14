"""Travel Buddy MVP - Configuration Settings

Centralized configuration for all service parameters, guardrails,
and cost-control levers as defined in the BRD.
"""

from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # --- App Metadata ---
    app_name: str = "Travel Buddy AI"
    app_version: str = "0.1.0-mvp"
    geo_fence: str = "dubai_uae"
    debug: bool = False  # Fail-closed: prod never trusts debug headers by default
    llm_debug: bool = False  # TB_LLM_DEBUG: verbose LiteLLM/OpenAI/httpx logging (separate from TB_DEBUG)

    # --- Database (Supabase / PostgreSQL) ---
    database_url: str = "postgresql://localhost:5432/travel_buddy"
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

    # --- Auth (Supabase JWT verification) ---
    # Project Settings -> API -> JWT Secret. Loaded from TB_SUPABASE_JWT_SECRET.
    supabase_jwt_secret: Optional[str] = None
    jwt_audience: str = "authenticated"

    # --- Anonymous identity (SPEC-09) ---
    # When True, accepts Authorization: Anonymous <uuid-v4> as a valid identity.
    # Defaults to False (fail-closed). Must be explicitly enabled for deployments
    # that accept device-only identities. Ignored when supabase_jwt_secret is set.
    allow_anonymous: bool = False

    # --- Model Gateway (LiteLLM) ---
    litellm_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None          # TB_GEMINI_API_KEY
    heavy_model: str = "gpt-4o"  # For structural rescheduling
    light_model: str = "gpt-4o-mini"  # For translations, simple QA (16x cheaper than gpt-4o)
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # --- Guardrail Levers (from BRD Section 2.3) ---
    # Lever 1: Reroute Throttle
    max_daily_reroutes_free: int = 5
    max_daily_reroutes_pro: int = 50

    # Lever 2: Semantic Cache
    semantic_cache_threshold: float = 0.92
    cache_ttl_hours: int = 24

    # Lever 3: Circuit Breaker
    max_loop_depth: int = 3

    # Lever 4: Asymmetric Routing (thresholds for intent classification)
    structural_intent_confidence: float = 0.7

    # Lever 5: Ad-Injection
    sponsored_boost_multiplier: float = 0.15

    # --- External APIs ---
    google_maps_api_key: Optional[str] = None
    google_places_api_key: Optional[str] = None
    openweather_api_key: Optional[str] = None

    # --- Payments (Stripe + RevenueCat) ---
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_price_monthly: Optional[str] = None
    stripe_price_yearly: Optional[str] = None
    revenuecat_api_key: Optional[str] = None
    revenuecat_webhook_auth: Optional[str] = None
    checkout_success_url: str = (
        "https://travelbuddy.app/upgrade/success?session_id={CHECKOUT_SESSION_ID}"
    )
    checkout_cancel_url: str = "https://travelbuddy.app/upgrade/cancel"

    # --- RAG Pipeline ---
    max_venue_results: int = 5
    transit_radius_km: float = 15.0
    hybrid_search_top_k: int = 10

    # --- CORS ---
    cors_allowed_origins: str = "*"  # TB_CORS_ALLOWED_ORIGINS (comma-separated for prod)

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = ConfigDict(
        env_file=".env",
        env_prefix="TB_",
        extra="ignore",
    )


# Singleton instance
settings = Settings()


def configure_provider_keys() -> None:
    """Export provider API keys to the env vars litellm/OpenAI expect."""
    import os
    if settings.litellm_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.litellm_api_key)
    if settings.gemini_api_key:
        os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)
