> **Product vision & strategy: see [docs/VISION.md](docs/VISION.md). This BRD covers technical spec.**

# TRAVEL BUDDY AI - MASTER BRD & TECHNICAL SPECIFICATION
## Version 4.0 | August 2026 | Dubai MVP

> **Purpose**: This is the single source of truth for the entire Travel Buddy project.
> Any AI coding agent, developer, or platform can ingest this document to resume work instantly.
>
> **See also**: [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) for current status, pending tasks, and Flutter integration notes.

---

## 1. PROJECT OVERVIEW

**What**: AI-powered travel companion backend with a continuous, self-correcting itinerary state loop.

**Core Problem**: Standard AI itineraries are static. When context changes (fatigue, weather, mood), regenerating breaks the timeline and erases locked reservations.

**Solution**: A state machine that maintains a live itinerary in memory, accepts real-time interruptions, intelligently replaces activities via RAG, and shifts the schedule while preserving locked items.

**Geo-fence**: Dubai, UAE (MVP). Expand globally after validation.

**Target**: Play Store deployment (Android first, iOS to follow).

**Repository**: `github.com/vneogi/travel-buddy` (branch: `main`)

---

## 2. WHAT'S ALREADY BUILT (Full Inventory)

### 2.1 Project Structure

```
travel-buddy/
├── main.py                          # FastAPI entry point (mounts trip + payment routers)
├── security.py                      # JWT auth (secret-first) + dev-mode fallback + ownership guard
├── seed_data.py                     # 16 curated Dubai venues (synthetic, for in-memory)
├── seed_supabase.py                 # Idempotent venue seeder for Supabase (real embeddings)
├── pyproject.toml                   # Ruff linter config + project metadata
├── requirements.txt                 # All dependencies (PyJWT, stripe, litellm, supabase, etc.)
├── requirements-prod.txt            # Full production dependencies
├── Dockerfile.py                    # Multi-stage production container
├── docker-compose.yml               # Local dev stack (app + pgvector + redis)
├── .env.example                     # All required environment variables
├── .github/workflows/ci.yml         # Lint (Ruff) -> Test -> Build -> Deploy
├── MASTER_BRD.md                    # THIS FILE
├── README.md                        # Quick start guide
│
├── config/
│   └── settings.py                  # All guardrail levers + env config (TB_ prefix)
│                                    # debug=False by default (fail-closed)
│                                    # cors_allowed_origins configurable
│                                    # extra="ignore" (tolerates unknown .env vars)
│
├── models/
│   ├── schemas.py                   # Pydantic models (TripState, TripNode w/ opening_hours)
│   └── database.py                  # PostgreSQL + pgvector schema SQL ($$-quoting fixed)
│
├── services/
│   ├── database_service.py          # In-memory DB (active backend for key-free testing)
│   │                                # Has consume_reroute() for atomic throttle
│   ├── supabase_service.py          # Supabase + pgvector (interface-compatible, OFF by default)
│   │                                # Has consume_reroute() via SQL RPC
│   ├── db_provider.py               # Provider seam: selects in-memory vs Supabase
│   ├── embedding_service.py         # Auto-detects real (LiteLLM) vs synthetic embeddings
│   ├── llm_service.py               # LiteLLM gateway + provider key wiring
│   ├── cache_service.py             # Semantic cache (Lever 2, cosine 0.92)
│   ├── maps_service.py              # Synthetic distance + check_venue_open()
│   ├── google_maps_real.py          # PRODUCTION: Real Distance Matrix + Places
│   ├── weather_service.py           # SCAFFOLDED: OpenWeatherMap (not wired into request path)
│   ├── payment_service.py           # RevenueCat + Stripe (real integration)
│   └── scheduler.py                 # Transit-aware rescheduling + hours validation
│
├── agents/
│   ├── state_machine.py             # Async LangGraph loop + circuit breaker (3 attempts)
│   └── router_agent.py              # Intent classifier + model router
│
├── routers/
│   ├── trip_router.py               # Trip CRUD + events (auth-gated, async)
│   │                                # Uses consume_reroute() (atomic, no TOCTOU race)
│   └── payment_router.py            # 6 payment endpoints (auth-gated)
│
├── pipeline/
│   ├── chunker.py                   # Semantic chunking (venue-aware)
│   └── rag_ingestion.py             # Full scrape->chunk->embed->store pipeline
│
├── monitoring/
│   └── cost_tracker.py              # SCAFFOLDED: LLM cost tracking (not wired into request path)
│
└── tests/                           # pytest suite (21 tests + 5 supabase-guarded)
    ├── __init__.py
    ├── conftest.py                  # Env isolation (clears JWT secret), TestClient, seed, reset
    ├── test_auth.py                 # 5 tests: public/401/403/ownership + auth-bypass regression
    ├── test_trip_flow.py            # 3 tests: create, get, light event, 404
    ├── test_throttle.py             # 1 test: 5/day limit, 403 on 6th (atomic)
    ├── test_payments.py             # 5 tests: plans, webhooks, expiry logic
    ├── test_scheduler.py            # 3 tests: deterministic scheduler (monkeypatched)
    ├── test_embedding.py            # 2 tests: synthetic determinism, cosine self-similarity
    └── test_supabase_integration.py # 5 tests: SKIPPED unless TB_SUPABASE_URL set
```

### 2.2 Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI app + routing | ✅ COMPLETE | Auth-gated, async, tested with pytest |
| Security (JWT + dev auth) | ✅ HARDENED | Secret-first ordering, debug=False default, regression-tested |
| State machine (async) | ✅ COMPLETE | Circuit breaker + transit-aware scheduler |
| Scheduler (transit-aware) | ✅ COMPLETE | Locked anchors, push-later logic, hours validation |
| Guardrail Lever 1 (throttle) | ✅ HARDENED | Atomic consume_reroute() closes TOCTOU race |
| Guardrail Lever 2 (cache) | ✅ COMPLETE | Cosine similarity 0.92 threshold |
| Guardrail Lever 3 (breaker) | ✅ COMPLETE | Max 3 attempts with candidate rotation |
| Guardrail Lever 4 (routing) | ✅ COMPLETE | Light/heavy classification |
| Guardrail Lever 5 (ads) | ✅ COMPLETE | Sponsored boost 0.15 in hybrid search |
| Venue seed data (16) | ✅ COMPLETE | Dubai venues with coordinates + opening_hours |
| Embedding service | ✅ COMPLETE | Auto-detects real (LiteLLM) vs synthetic |
| LLM service (LiteLLM) | ✅ VERIFIED | GPT-4o + gpt-4o-mini working (real keys active) |
| Supabase DB schema | ✅ DEPLOYED | 5 tables + 5 functions live in Supabase cloud |
| Supabase service | ✅ COMPLETE | Interface-compatible, OFF until import swap |
| Payment service | ✅ COMPLETE | RevenueCat + Stripe, webhooks fail-closed |
| CORS | ✅ HARDENED | Configurable origins, no invalid *+credentials combo |
| Docker deployment | ✅ COMPLETE | Multi-stage build + docker-compose |
| CI/CD (GitHub Actions) | ✅ COMPLETE | Ruff lint + pyproject.toml -> Test -> Build -> Deploy |
| Test suite (pytest) | ✅ COMPLETE | 21 passed + 5 skipped, env-isolated, ~18s |

---

## 3. ARCHITECTURE

### 3.1 Request Flow

```
Mobile App (Flutter)
    │
    ▼
[FastAPI Router] ─── Auth: JWT verify (prod) / X-Debug-User-Id (dev, only when no secret)
    │                 Lever 1: Atomic consume_reroute() (reserve-first)
    ▼
[State Machine (async)]
    ├─ Node 1: Classify Intent (Lever 4: light vs heavy)
    ├─ Node 2: Check Semantic Cache (Lever 2)
    ├─ Node 3: Hybrid Venue Search (Lever 5: sponsored boost)
    ├─ Node 4: Apply Structural Edit (Lever 3: circuit breaker, 3 attempts)
    │          └─ Scheduler: transit-aware, respects locked anchors + hours
    └─ Node 5: Update Trip State
    │
    ▼
[In-Memory DB (dev) / Supabase PostgreSQL + pgvector (prod)]
```

### 3.2 Model Routing

| Intent Type | Model | Cost/1K tokens | Use Case |
|-------------|-------|----------------|----------|
| Structural (reroute, swap, cancel, add) | GPT-4o | $0.0025 in / $0.01 out | Itinerary rewrites |
| Informational (translate, info) | gpt-4o-mini | $0.00015 in / $0.0006 out | Simple QA (16x cheaper) |
| Embedding | text-embedding-3-small | $0.00002 | Vector search |

**Fallback chains**:
- LIGHT: `["gpt-4o-mini"]` (Gemini removed — wrong key type, VertexAI routing issue)
- HEAVY: `["gpt-4o", "claude-3-5-sonnet-20241022", "gemini/gemini-1.5-pro"]`

### 3.3 Auth Contract

- **All endpoints except** `GET /health` and `GET /api/v1/payment/plans` **require auth**
- **Production**: `Authorization: Bearer <supabase_jwt>` — verified against `TB_SUPABASE_JWT_SECRET`
- **Dev mode** (`TB_DEBUG=true` AND no JWT secret configured): `X-Debug-User-Id: <user_id>` header
- **CRITICAL**: When JWT secret IS configured, debug header is IGNORED (fail-closed). This prevents the auth-bypass where an attacker sends `X-Debug-User-Id` to impersonate users.
- `user_id` in request bodies is `Optional[str] = None` and ignored (extracted from token/header)
- Trip endpoints enforce ownership: requesting another user's trip returns 403

---

## 4. API CONTRACT

### Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | Public | App info |
| GET | `/api/v1/health` | Public | Health check |
| GET | `/api/v1/user/status` | Required | Tier + reroute info |
| POST | `/api/v1/trip/create` | Required | Create Dubai itinerary |
| GET | `/api/v1/trip/{trip_id}` | Required + Owner | Get trip state |
| POST | `/api/v1/trip/event` | Required + Owner | **Main endpoint** - process events |
| GET | `/api/v1/venues/search` | Required | RAG venue search |
| GET | `/api/v1/stats` | Required | System analytics |
| GET | `/api/v1/payment/plans` | Public | Available subscription plans |
| GET | `/api/v1/payment/status` | Required | User subscription status |
| POST | `/api/v1/payment/checkout` | Required | Stripe checkout session |
| POST | `/api/v1/payment/verify-purchase` | Required | Mobile IAP verify (RevenueCat) |
| POST | `/api/v1/payment/webhook/stripe` | Signature-verified | Stripe webhook events |
| POST | `/api/v1/payment/webhook/revenuecat` | Auth-verified | RevenueCat webhook events |

### Main Event Request (POST /api/v1/trip/event)

```json
{
  "trip_id": "uuid",
  "event_type": "cancel_activity|swap_activity|add_activity|change_mood|weather_alert|translate|ask_info|reroute",
  "message": "natural language input",
  "target_node_id": "optional - node to modify",
  "preferences": {"vibe_tags": [], "mood": "", "audience": []}
}
```

**Note**: `user_id` is NOT passed in the body — it's extracted from the auth token/header.

### Event Classification

| Category | Events | Model Used |
|----------|--------|------------|
| Structural (VENUE_REQUIRED) | swap_activity, add_activity, reroute | Heavy (GPT-4o) |
| Structural (no venue) | cancel_activity | Heavy (GPT-4o) |
| Informational | ask_info, translate, change_mood, weather_alert | Light (gpt-4o-mini) |

---

## 5. DATABASE SCHEMA

Full SQL in `models/database.py` + `services/supabase_service.py`. Key tables:

- **user_tiers**: user_id, tier_status, daily_reroute_count, max_daily_reroutes, last_reset_date
- **trip_states**: trip_id, user_id, state_json (JSONB), is_active
- **venues_rag**: name, description, lat/lng, vibe_tags[], opening_hours, embedding VECTOR(1536), is_sponsored, bid_weight
- **cached_responses**: query_embedding VECTOR(1536), cached_response_text, expires_at, hit_count
- **event_log**: user_id, event_type, routing_tier, from_cache, token_cost_estimate

### SQL Functions (all use valid `$$` dollar-quoting):

| Function | Purpose |
|----------|---------|
| `reset_daily_reroutes()` | Cron: resets all user counts at midnight |
| `hybrid_venue_search(...)` | pgvector cosine + distance filter + sponsored boost; returns lat, lng, opening_hours |
| `increment_reroute(user_id)` | Atomic counter increment (kept for compatibility) |
| `consume_reroute(user_id)` | Atomic check-and-increment (closes quota race condition) — **used by throttle** |
| `check_semantic_cache(...)` | Vector similarity search on cache table |

### Supabase Status

| Item | Status |
|------|--------|
| Schema (5 tables) | ✅ Deployed to `xqpcuakugxmcrollablz.supabase.co` |
| Functions (5) | ✅ Deployed |
| Indexes (7) | ✅ Deployed |
| Extensions (vector, postgis) | ✅ Enabled |
| Venue data (16 Dubai venues) | ⏳ Not yet seeded (run `python seed_supabase.py` after import swap) |
| Backend flip (3 import swaps) | ⏳ Not done — app still uses in-memory |

---

## 6. ENVIRONMENT VARIABLES

All prefixed with `TB_`. See `.env.example` for full list.

```bash
# --- Database ---
TB_SUPABASE_URL=              # Supabase project URL
TB_SUPABASE_KEY=              # Supabase service role key (sb_secret_...)

# --- Auth ---
TB_SUPABASE_JWT_SECRET=       # JWT verification secret (HS256, from Supabase dashboard)
TB_DEBUG=false                # DEFAULT IS FALSE. Set true only for local dev.

# --- AI Models ---
TB_LITELLM_API_KEY=           # OpenAI API key (enables real GPT-4o + embeddings)
TB_GEMINI_API_KEY=            # Google Gemini API key (not currently used)

# --- CORS ---
TB_CORS_ALLOWED_ORIGINS=*     # Comma-separated origins for prod (e.g. https://travelbuddy.app)

# --- External APIs ---
TB_GOOGLE_MAPS_API_KEY=       # Google Maps Distance Matrix + Places
TB_OPENWEATHER_API_KEY=       # OpenWeatherMap (free tier, no card)

# --- Payments ---
TB_STRIPE_SECRET_KEY=         # Stripe secret key
TB_STRIPE_WEBHOOK_SECRET=     # Stripe webhook signing secret
TB_STRIPE_PRICE_MONTHLY=      # Stripe Price ID for monthly plan
TB_STRIPE_PRICE_YEARLY=       # Stripe Price ID for yearly plan
TB_REVENUECAT_API_KEY=        # RevenueCat API key
TB_REVENUECAT_WEBHOOK_AUTH=   # Exact Authorization header value from RC webhooks
```

### Key Status (What's Active)

| Key | Status | Notes |
|-----|--------|-------|
| TB_LITELLM_API_KEY | ✅ Working | OpenAI sk-proj-... (billing active, GPT-4o + mini + embeddings) |
| TB_GEMINI_API_KEY | ❌ Invalid | Wrong format (not AIza...). Not blocking — removed from fallback |
| TB_SUPABASE_URL | ✅ Configured | https://xqpcuakugxmcrollablz.supabase.co |
| TB_SUPABASE_KEY | ✅ Configured | sb_secret_... (service role) |
| TB_SUPABASE_JWT_SECRET | ✅ Configured | HS256 shared secret (legacy mode) |
| TB_DEBUG | ✅ Set | true (in .env for local dev) |

---

## 7. MOBILE APP SPECIFICATION (For Flutter Agent)

### Tech Stack
- **Framework**: Flutter 3.x (Dart)
- **State Management**: Riverpod
- **Navigation**: GoRouter
- **HTTP**: Dio or http package
- **Maps**: google_maps_flutter
- **Auth**: Supabase Auth (magic link + Google Sign-In)
- **Payments**: RevenueCat Flutter SDK
- **Push**: Firebase Cloud Messaging

### Screens Required
1. **Onboarding** - Mood selection, travel style quiz (3 screens)
2. **Home/Trip List** - Active trips, create new trip
3. **Live Itinerary** - Timeline view with draggable/lockable activity cards
4. **Activity Detail** - Venue info, swap button, transit time
5. **Swap Sheet** - Bottom sheet with RAG suggestions, filter by vibe
6. **Map View** - Google Maps with venue pins, transit polylines
7. **Chat** - Natural language input (WebSocket real-time)
8. **Profile** - Settings, tier status, upgrade CTA
9. **Upgrade** - Plan comparison, RevenueCat paywall

### Key UX Patterns
- Locked activities show a padlock icon and cannot be swiped
- Weather alerts appear as a banner with one-tap "swap to indoor"
- Remaining reroutes shown as a counter badge ("3 left today")
- Cache hits should feel instant (no loading spinner)
- Heavy model responses show a brief "thinking" animation

### API Integration
- Base URL: configurable via environment (dev/staging/prod)
- Auth: Bearer token (Supabase JWT) in Authorization header
- WebSocket for real-time chat: `ws://api/v1/chat/{trip_id}`

---

## 8. DEPLOYMENT PLAYBOOK

### Option A: Railway (Recommended for MVP)
```bash
# 1. Push to GitHub
# 2. Connect Railway to repo
# 3. Set env vars in Railway dashboard (copy from .env, set TB_DEBUG=false)
# 4. Railway auto-deploys from Dockerfile on push to main
```

### Option B: Docker Compose (Local Dev)
```bash
docker-compose up -d  # Starts app + pgvector + redis
open http://localhost:8000/docs
```

### Option C: Google Cloud Run
```bash
gcloud run deploy travel-buddy --source . --region me-central1
```

---

## 9. MONETIZATION MODEL

| Tier | Price | Features |
|------|-------|----------|
| Free | $0 | 5 reroutes/day, light model only, sponsored results |
| Pro Monthly | $4.99/mo | 50 reroutes/day, GPT-4o, no sponsored, priority |
| Pro Yearly | $39.99/yr | Same as monthly, 2 months free |

**Revenue streams**:
- Subscriptions (RevenueCat/Stripe)
- Sponsored venues (bid_weight * 0.15 boost in RAG results)
- Affiliate links (future: hotel/restaurant bookings)

---

## 10. TEST SUITE

```bash
# Run all tests (no API keys needed, uses dev-auth + synthetic data)
pip install -r requirements.txt
pytest -q

# Expected output:
# .....................                              [100%]
# 21 passed, 5 skipped, 10 warnings in ~18s
```

### Test Coverage

| File | Tests | What's Verified |
|------|-------|-----------------|
| test_auth.py | 5 | Health public, 401 w/o auth, dev-auth works, ownership (403), **auth-bypass regression** |
| test_trip_flow.py | 3 | Event requires auth, create+light event, unknown trip 404 |
| test_throttle.py | 1 | 5 reroutes succeed (atomic), 6th returns 403 |
| test_payments.py | 5 | Plans public, webhook auth, RC upgrade, Stripe sig, expiry |
| test_scheduler.py | 3 | Unreachable-lock conflict, feasible preserves times, skipped excluded |
| test_embedding.py | 2 | Synthetic determinism + normalized, cosine self-similarity |
| test_supabase_integration.py | 5 (skipped) | User CRUD, trip persist, atomic quota, venue count, hybrid search |

### Test Environment Isolation

`tests/conftest.py` overrides `TB_SUPABASE_JWT_SECRET`, `TB_SUPABASE_URL`, `TB_SUPABASE_KEY` to empty strings and sets `TB_DEBUG=true` before importing the app. This ensures tests always run in dev-auth mode regardless of what's in the developer's `.env` file.

---

## 11. IMPLEMENTATION HISTORY

| # | Commit | What Changed |
|---|--------|--------------|
| 1 | `feat: Initial Travel Buddy MVP` | Full synthetic MVP backend |
| 2 | `fix(security)` | JWT auth + dev fallback, trip ownership, closed IDOR holes |
| 3 | `fix(payments)` | Wired payment_router, 6 auth-gated endpoints, webhooks fail-closed |
| 4 | `feat(ai)` | Auto-detect embeddings, async state machine, LLM wired into loop |
| 5 | `feat(tests)` | 20-test pytest suite, $$-quoting fix, Supabase parity |
| 6 | `fix(settings)` | Restored supabase_jwt_secret + jwt_audience |
| 7 | `fix(sql)` | All 5 PL/pgSQL functions confirmed valid $$ |
| 8 | `docs: BRD v3.0` | Full documentation update |
| 9 | `fix(config)` | Light model → gpt-4o-mini |
| 10 | `fix(llm)` | Removed dead Gemini from LIGHT_FALLBACK |
| 11 | `feat: Supabase seeder + CORS + atomic throttle` | seed_supabase.py, integration tests, configurable CORS, consume_reroute() |
| 12 | `fix(ci)` | Added pyproject.toml for Ruff linter |
| 13 | `security: Fix auth-bypass regression` | **CRITICAL** — reverted debug-header-first ordering, debug=False default, env isolation, regression test |

---

## 12. SECURITY NOTES

### Auth-Bypass Incident (Commit #13)

A code change during commit #11 inadvertently moved the `X-Debug-User-Id` check BEFORE the JWT verification. Combined with `debug=True` as the default, this meant any client could impersonate any user by sending a single header — bypassing all authentication.

**Root cause**: The test suite failed when `.env` contained `TB_SUPABASE_JWT_SECRET` (which correctly enables JWT mode). The fix was applied to the app's auth logic instead of the test environment.

**Correct fix applied**:
1. `security.py`: JWT secret check ALWAYS comes first. Debug header only works when no secret is configured.
2. `settings.py`: `debug` defaults to `False` (fail-closed).
3. `tests/conftest.py`: Env isolation — overrides JWT secret to empty before app import.
4. `tests/test_auth.py`: Regression test proving `X-Debug-User-Id` returns 401 when secret is set.

**Lesson**: Never weaken production security to fix test failures. Fix the test environment instead.

---

## 13. REMAINING WORK

### Immediate (Before Supabase Flip)
| Task | Priority | Notes |
|------|----------|-------|
| Seed venues to Supabase (`python seed_supabase.py`) | HIGH | Requires running locally with real API key |
| Flip imports (3 files) to Supabase backend | HIGH | The 3 import swaps in trip_router, payment_router, state_machine |
| Run `pytest tests/test_supabase_integration.py` with creds | HIGH | Verify live Supabase path |
| Deploy to Railway / Cloud Run | HIGH | First live deployment |

### Deferred (Post-Deploy)
| Task | Priority | Notes |
|------|----------|-------|
| Replace datetime.utcnow() with datetime.now(UTC) | LOW | Deprecation warnings (cosmetic) |
| Regenerate Gemini key (AIza... format from aistudio.google.com) | LOW | Currently unused |
| Add weather_alert / change_mood auto-swap | LOW | Currently informational only |

### Future Phases
| Phase | Task | Owner | Priority |
|-------|------|-------|----------|
| 3 | Flutter mobile app | Coding Agent | HIGH |
| 3 | UX/UI Design (Figma) | Human Designer | HIGH |
| 4 | RevenueCat + Stripe integration testing | Dev | HIGH |
| 5 | Security audit | Human Security Eng | MEDIUM |
| 5 | Legal (Privacy Policy, ToS) | Lawyer | MEDIUM |
| 5 | Play Store listing + ASO | Human | MEDIUM |
| 6 | Venue partnerships (Dubai) | Business Dev | LOW (post-launch) |
| 6 | Load testing (k6) | Either | LOW |

---

## 14. QUICK START (For Any Developer/Agent)

```bash
# 1. Clone
git clone https://github.com/vneogi/travel-buddy.git
cd travel-buddy

# 2. Install
pip install -r requirements.txt

# 3. Run tests (no external deps needed — .env vars are overridden by conftest)
pytest -q
# -> 21 passed, 5 skipped in ~18s

# 4. Run server with synthetic data
TB_DEBUG=true python main.py
# -> http://localhost:8000/docs

# 5. Test an endpoint (dev-mode auth — only works when NO JWT secret is set)
curl -H "X-Debug-User-Id: test-user-1" http://localhost:8000/api/v1/user/status

# 6. For Supabase integration:
#    a. Copy .env.example to .env, fill in Supabase + OpenAI keys
#    b. Run schema SQL in Supabase SQL Editor (from models/database.py + services/supabase_service.py)
#    c. python seed_supabase.py  (seeds 16 venues with real embeddings)
#    d. Swap 3 imports: database_service -> db_provider (see Section 15)
#    e. pytest tests/test_supabase_integration.py -v

# 7. For production deployment:
docker-compose up -d
# OR: Railway / Cloud Run (set TB_DEBUG=false, provide all keys)
```

---

## 15. PERSISTENCE BACKEND SWITCHING

The app defaults to **in-memory** (no external deps). To switch to Supabase:

1. Set `TB_SUPABASE_URL`, `TB_SUPABASE_KEY`, `TB_SUPABASE_JWT_SECRET` in .env
2. Run the SQL from `models/database.py` (`SCHEMA_SQL`) against your Supabase database ✅ DONE
3. Run the SQL from `services/supabase_service.py` (`ADDITIONAL_SQL_FUNCTIONS`) ✅ DONE
4. Run `python seed_supabase.py` to populate venues with real embeddings
5. Change imports in `routers/trip_router.py`, `routers/payment_router.py`, `agents/state_machine.py`:
   - FROM: `from services.database_service import db_service`
   - TO: `from services.db_provider import db as db_service`
6. Run `pytest tests/test_supabase_integration.py -v` to verify
7. Run full suite to confirm nothing regressed

---

*Last updated: August 4, 2026*
*Built by: Vikrant Neogi + Genie Code*
*Version: 4.0 (Supabase schema deployed, security hardened, atomic throttle, 21 tests green)*
