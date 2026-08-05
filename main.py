"""Travel Buddy MVP - FastAPI Application Entry Point

Launch with: uvicorn main:app --reload --port 8000
Docs available at: http://localhost:8000/docs
"""

import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from routers.trip_router import router as trip_router
try:
    from routers.payment_router import router as payment_router
except ImportError:
    payment_router = None
from routers.signal_router import router as signal_router
from seed_data import seed_venues

# ==============================================================================
# App Initialization
# ==============================================================================

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI-powered travel companion backend. Dubai MVP.\n\n"
        "Features:\n"
        "- Continuous self-correcting itinerary state loop\n"
        "- Asymmetric model routing (light vs heavy)\n"
        "- Semantic caching to minimize LLM costs\n"
        "- Hybrid RAG search with sponsored boost\n"
        "- 5-reroute daily throttle for free users\n"
        "- Circuit breaker for runaway agent loops"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for mobile app access
_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
_allow_all = _origins == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # "*" + credentials is an invalid/unsafe combo. The API authenticates via
    # a Bearer header (not cookies), so credentials aren't needed for "*".
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(trip_router)
if payment_router:
    app.include_router(payment_router)
app.include_router(signal_router)


# ==============================================================================
# Startup Events
# ==============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup."""
    print(f"\n{'='*60}")
    print(f"  {settings.app_name} v{settings.app_version}")
    print(f"  Geo-fence: {settings.geo_fence}")
    print(f"  Debug mode: {settings.debug}")
    print(f"{'='*60}")

    # Seed venue data
    venue_count = seed_venues()
    print(f"  Loaded {venue_count} Dubai venues into RAG store")
    print(f"  Guardrails active:")
    print(f"    - Max reroutes (free): {settings.max_daily_reroutes_free}/day")
    print(f"    - Cache threshold: {settings.semantic_cache_threshold}")
    print(f"    - Circuit breaker: {settings.max_loop_depth} loops")
    print(f"    - Sponsored boost: {settings.sponsored_boost_multiplier}")
    print(f"{'='*60}\n")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/v1/health",
        "geo_fence": settings.geo_fence,
    }


# ==============================================================================
# Run directly
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
