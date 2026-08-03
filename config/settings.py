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

    # --- Auth (Supabase JWT verification) ---
    # Project Settings -> API -> JWT Secret. Loaded from TB_SUPABASE_JWT_SECRET.
    supabase_jwt_secret: Optional[str] = None
    jwt_audience: str = "authenticated"

    # --- Model Gateway (LiteLLM) ---
    litellm_api_key: Optional[str] = None
    heavy_model: str = "gpt-4o"  # For structural rescheduling
    light_model: str = "gemini-1.5-flash"  # For translations, simple QA
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
