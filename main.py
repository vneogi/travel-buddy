"""Travel Buddy MVP - FastAPI Application Entry Point

Launch with: uvicorn main:app --reload --port 8000
Docs available at: http://localhost:8000/docs
"""

import logging
import sys
import os
import time
import traceback as tb_module
import uuid
from contextlib import asynccontextmanager

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from routers.trip_router import router as trip_router
try:
    from routers.payment_router import router as payment_router
except ImportError:
    payment_router = None
from routers.signal_router import router as signal_router
from routers.debug_router import router as debug_router
from monitoring.error_log import error_log
from seed_data import seed_venues

# ==============================================================================
# Logging Configuration (SPEC-05: use logging, not print)
# ==============================================================================

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
logger = logging.getLogger("travelbuddy")

# ─── Silence third-party loggers ─────────────────────────────────────────────
# LiteLLM, OpenAI, and httpx/httpcore log full request bodies (including
# embedding arrays, system prompts, and Authorization headers) at DEBUG.
# TB_DEBUG=true is needed for the debug user header and must NOT enable this.
# Gate verbose LLM logging behind a separate TB_LLM_DEBUG flag.
_llm_log_level = logging.DEBUG if settings.llm_debug else logging.WARNING
for _noisy in (
    "LiteLLM",
    "litellm",
    "LiteLLM Proxy",
    "LiteLLM Router",
    "openai",
    "openai._base_client",
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
):
    logging.getLogger(_noisy).setLevel(_llm_log_level)

# Also suppress litellm's own verbose flag (separate from Python logging).
try:
    import litellm
    litellm.set_verbose = bool(settings.llm_debug)
    litellm.suppress_debug_info = not settings.llm_debug
except ImportError:
    pass

# ==============================================================================
# Lifespan (replaces deprecated @app.on_event("startup"))
# ==============================================================================

@asynccontextmanager
async def _lifespan(app):
    """Application lifespan: startup logic runs before yield, shutdown after."""
    venue_count = seed_venues()
    logger.info("=" * 60)
    logger.info("%s v%s", settings.app_name, settings.app_version)
    logger.info("Geo-fence: %s | Debug: %s", settings.geo_fence, settings.debug)
    logger.info("Venues loaded: %d", venue_count)
    # Booleans only — NEVER log key values.
    logger.info(
        "Config: llm_key_present=%s supabase_configured=%s jwt_auth=%s cors=%s",
        bool(settings.litellm_api_key),
        bool(getattr(settings, "supabase_url", None) and getattr(settings, "supabase_key", None)),
        bool(getattr(settings, "supabase_jwt_secret", None)),
        settings.cors_allowed_origins,
    )
    logger.info(
        "Guardrails: reroutes=%d/day cache=%.2f breaker=%d boost=%.2f",
        settings.max_daily_reroutes_free,
        settings.semantic_cache_threshold,
        settings.max_loop_depth,
        settings.sponsored_boost_multiplier,
    )
    logger.info("=" * 60)
    yield
    # Shutdown: nothing to clean up currently.


# ==============================================================================
# App Initialization
# ==============================================================================

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=_lifespan,
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
app.include_router(debug_router)


# ==============================================================================
# Observability (SPEC-05)
# ==============================================================================

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Attach a request_id and log method/path/status/duration for every request."""
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # The exception handler below records details; log timing and re-raise.
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.error(
            "%s %s -> EXCEPTION in %dms request_id=%s",
            request.method, request.url.path, duration_ms, request_id,
        )
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "%s %s -> %d in %dms request_id=%s",
        request.method, request.url.path, response.status_code, duration_ms, request_id,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the FULL traceback for any unhandled exception. No silent 500s."""
    request_id = getattr(request.state, "request_id", "unknown")
    tb = tb_module.format_exception(type(exc), exc, exc.__traceback__)
    tb_str = "".join(tb)
    logger.error(
        "Unhandled %s on %s %s request_id=%s\n%s",
        type(exc).__name__, request.method, request.url.path, request_id, tb_str,
    )
    error_log.record(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=500,
        exc_type=type(exc).__name__,
        message=str(exc),
        traceback_str=tb_str,
    )
    # Response carries only the request_id — never internal details.
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation failures — this bug class (Pydantic extra field) cost hours."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning(
        "Validation error on %s %s request_id=%s: %s",
        request.method, request.url.path, request_id, exc.errors(),
    )
    error_log.record(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=422,
        exc_type="RequestValidationError",
        message=str(exc.errors()),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "request_id": request_id},
    )







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
