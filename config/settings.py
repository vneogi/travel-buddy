"""Travel Buddy MVP - Configuration Settings

Centralized configuration for all service parameters, guardrails,
and cost-control levers as defined in the BRD.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # --- App Metadata ---
    app_name: str = "Travel Buddy AI"
    app_version: str = "0.1.0-mvp"
    geo_fence: str = "dubai_uae"
    debug: bool = True

    # --- Database (Supabase / PostgreSQL) ---
    database_url: str = "postgresql://localhost:5432/travel_buddy"
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

    # --- Auth (JWT from Supabase) ---
    supabase_jwt_secret: Optional[str] = None  # TB_SUPABASE_JWT_SECRET
    jwt_audience: str = "authenticated"

    # --- Model Gateway (LiteLLM) ---
    litellm_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None          # TB_GEMINI_API_KEY
    heavy_model: str = "gpt-4o"  # For structural rescheduling
    light_model: str = "gemini/gemini-1.5-flash"  # For translations, simple QA
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

    # --- Payments (Stripe + RevenueCat) ---
    stripe_secret_key: Optional[str] = None        # TB_STRIPE_SECRET_KEY
    stripe_webhook_secret: Optional[str] = None     # TB_STRIPE_WEBHOOK_SECRET
    stripe_price_monthly: Optional[str] = None      # TB_STRIPE_PRICE_MONTHLY (price_...)
    stripe_price_yearly: Optional[str] = None       # TB_STRIPE_PRICE_YEARLY  (price_...)
    revenuecat_api_key: Optional[str] = None        # TB_REVENUECAT_API_KEY
    # The exact string RevenueCat sends in the webhook Authorization header
    # (Dashboard -> Integrations -> Webhooks -> Authorization header value).
    revenuecat_webhook_auth: Optional[str] = None   # TB_REVENUECAT_WEBHOOK_AUTH
    checkout_success_url: str = (
        "https://travelbuddy.app/upgrade/success?session_id={CHECKOUT_SESSION_ID}"
    )
    checkout_cancel_url: str = "https://travelbuddy.app/upgrade/cancel"

    # --- RAG Pipeline ---
    max_venue_results: int = 5
    transit_radius_km: float = 15.0
    hybrid_search_top_k: int = 10

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_prefix = "TB_"


# Singleton instance
settings = Settings()


def configure_provider_keys() -> None:
    """Export provider API keys to the env vars litellm/OpenAI expect.

    litellm resolves credentials per-model from these standard env vars, so we
    set them once from our TB_-prefixed settings.
    """
    import os
    if settings.litellm_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.litellm_api_key)
    if settings.gemini_api_key:
        os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)
