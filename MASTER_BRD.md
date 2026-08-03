# TRAVEL BUDDY AI - MASTER BRD & TECHNICAL SPECIFICATION
## Version 3.0 | August 2026 | Dubai MVP

> **Purpose**: This is the single source of truth for the entire Travel Buddy project.
> Any AI coding agent, developer, or platform can ingest this document to resume work instantly.

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
├── security.py                      # JWT auth + dev-mode fallback + trip ownership guard
├── seed_data.py                     # 16 curated Dubai venues (synthetic)
├── requirements.txt                 # All dependencies (PyJWT, stripe, litellm, etc.)
├── requirements-prod.txt            # Full production dependencies
├── Dockerfile.py                    # Multi-stage production container
├── docker-compose.yml               # Local dev stack (app + pgvector + redis)
├── .env.example                     # All required environment variables
├── .github/workflows/ci.yml         # Lint -> Test -> Build -> Deploy
├── MASTER_BRD.md                    # THIS FILE
├── README.md                        # Quick start guide
│
├── config/
│   └── settings.py                  # All guardrail levers + env config (TB_ prefix)
│
├── models/
│   ├── schemas.py                   # Pydantic models (TripState, TripNode w/ opening_hours)
│   └── database.py                  # PostgreSQL + pgvector schema SQL ($$-quoting fixed)
│
├── services/
│   ├── database_service.py          # In-memory DB (active backend for key-free testing)
│   ├── supabase_service.py          # Supabase + pgvector (interface-compatible, OFF by default)
│   ├── db_provider.py               # Provider seam: selects in-memory vs Supabase
│   ├── embedding_service.py         # Auto-detects real (LiteLLM) vs synthetic embeddings
│   ├── llm_service.py               # LiteLLM gateway + provider key wiring
│   ├── cache_service.py             # Semantic cache (Lever 2, cosine 0.92)
│   ├── maps_service.py              # Synthetic distance + check_venue_open()
│   ├── google_maps_real.py          # PRODUCTION: Real Distance Matrix + Places
│   ├── weather_service.py           # PRODUCTION: OpenWeatherMap + Dubai alerts
│   ├── payment_service.py           # RevenueCat + Stripe (real integration)
│   └── scheduler.py                 # Transit-aware rescheduling + hours validation
│
├── agents/
│   ├── state_machine.py             # Async LangGraph loop + circuit breaker (3 attempts)
│   └── router_agent.py              # Intent classifier + model router
│
├── routers/
│   ├── trip_router.py               # Trip CRUD + events (auth-gated, async)
│   └── payment_router.py            # 6 payment endpoints (auth-gated)
│
├── pipeline/
│   ├── chunker.py                   # Semantic chunking (venue-aware)
│   └── rag_ingestion.py             # Full scrape->chunk->embed->store pipeline
│
├── monitoring/
│   └── cost_tracker.py              # LLM cost tracking + budget alerts
│
└── tests/                           # pytest suite (20 tests, key-free)
    ├── __init__.py
    ├── conftest.py                  # TestClient, dev-auth helper, seed, reset
    ├── test_auth.py                 # Public/401/403/ownership tests
    ├── test_trip_flow.py            # Create, get, light event, 404
    ├── test_throttle.py             # 5/day limit, 403 on 6th
    ├── test_payments.py             # Plans, webhooks, expiry logic
    ├── test_scheduler.py            # Deterministic scheduler tests (monkeypatched)
    └── test_embedding.py            # Synthetic determinism, cosine self-similarity
```

### 2.2 Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI app + routing | ✅ COMPLETE | Auth-gated, async, tested with pytest |
| Security (JWT + dev auth) | ✅ COMPLETE | Supabase JWT in prod, X-Debug-User-Id in dev |
| State machine (async) | ✅ COMPLETE | Circuit breaker + transit-aware scheduler |
| Scheduler (transit-aware) | ✅ COMPLETE | Locked anchors, push-later logic, hours validation |
| Guardrail Lever 1 (throttle) | ✅ COMPLETE | Blocks at limit with 403 |
| Guardrail Lever 2 (cache) | ✅ COMPLETE | Cosine similarity 0.92 threshold |
| Guardrail Lever 3 (breaker) | ✅ COMPLETE | Max 3 attempts with candidate rotation |
| Guardrail Lever 4 (routing) | ✅ COMPLETE | Light/heavy classification |
| Guardrail Lever 5 (ads) | ✅ COMPLETE | Sponsored boost 0.15 in hybrid search |
| Venue seed data (16) | ✅ COMPLETE | Dubai venues with coordinates + opening_hours |
| Embedding service | ✅ COMPLETE | Auto-detects real (LiteLLM) vs synthetic |
| LLM service (LiteLLM) | ✅ COMPLETE | GPT-4o + Gemini Flash + provider key wiring |
| Supabase service | ✅ COMPLETE | Interface-compatible, OFF until keys configured |
| Payment service | ✅ COMPLETE | RevenueCat + Stripe, webhooks fail-closed |
| Weather service | ✅ COMPLETE | OpenWeatherMap + Dubai-specific alerts |
| Google Maps (real) | ✅ COMPLETE | Distance Matrix + Places (New) API |
| RAG pipeline | ✅ COMPLETE | TimeOut + Reddit scrapers + semantic chunking |
| Cost monitoring | ✅ COMPLETE | Per-user attribution + budget alerts |
| Docker deployment | ✅ COMPLETE | Multi-stage build + docker-compose |
| CI/CD (GitHub Actions) | ✅ COMPLETE | Lint -> Test -> Build -> Deploy |
| Test suite (pytest) | ✅ COMPLETE | 20 tests, all pass, key-free, 0.42s |
| SQL schema ($$-fixed) | ✅ COMPLETE | All 5 PL/pgSQL functions valid |

---

## 3. ARCHITECTURE

### 3.1 Request Flow

```
Mobile App (Flutter)
    │
    ▼
[FastAPI Router] ─── Auth: JWT verify (prod) / X-Debug-User-Id (dev)
    │                 Lever 1: Check reroute quota
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
| Informational (translate, info) | Gemini 1.5 Flash | $0.000075 in / $0.0003 out | Simple QA |
| Embedding | text-embedding-3-small | $0.00002 | Vector search |

### 3.3 Auth Contract

- **All endpoints except** `GET /health` and `GET /api/v1/payment/plans` **require auth**
- **Production**: `Authorization: Bearer <supabase_jwt>` — verified against `TB_SUPABASE_JWT_SECRET`
- **Dev mode** (`TB_DEBUG=true`, no JWT secret): `X-Debug-User-Id: <user_id>` header
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
| Informational | ask_info, translate, change_mood, weather_alert | Light (Gemini Flash) |

---

## 5. DATABASE SCHEMA

Full SQL in `models/database.py`. Key tables:

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
| `increment_reroute(user_id)` | Atomic counter increment |
| `consume_reroute(user_id)` | Atomic check-and-increment (closes quota race condition) |
| `check_semantic_cache(...)` | Vector similarity search on cache table |

---

## 6. ENVIRONMENT VARIABLES

All prefixed with `TB_`. See `.env.example` for full list.

```bash
# --- Database ---
TB_SUPABASE_URL=              # Supabase project URL
TB_SUPABASE_KEY=              # Supabase anon/service key

# --- Auth ---
TB_SUPABASE_JWT_SECRET=       # JWT verification secret (from Supabase dashboard)
TB_DEBUG=true                 # Enables dev-mode auth (X-Debug-User-Id header)

# --- AI Models ---
TB_LITELLM_API_KEY=           # OpenAI API key (enables real embeddings + GPT-4o)
TB_GEMINI_API_KEY=            # Google Gemini API key (enables Gemini Flash)

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

### Key Setup Priority (for going live):
1. **None needed** — app runs fully with synthetic data (in-memory DB, mock embeddings)
2. **TB_LITELLM_API_KEY** — enables real GPT-4o + embeddings
3. **TB_GEMINI_API_KEY** — enables Gemini Flash for light model
4. **TB_SUPABASE_URL + KEY + JWT_SECRET** — enables real DB + real auth
5. **TB_GOOGLE_MAPS_API_KEY** — real transit times + venue data
6. **TB_OPENWEATHER_API_KEY** — weather alerts (free tier)
7. **Stripe + RevenueCat** — when Flutter app is ready for payments

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
# 3. Set env vars in Railway dashboard
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
# .................... [100%]
# 20 passed, 21 warnings in 0.42s
```

### Test Coverage

| File | Tests | What's Verified |
|------|-------|-----------------|
| test_auth.py | 4 | Health public, 401 w/o auth, dev-auth works, trip ownership (403) |
| test_trip_flow.py | 3 | Event requires auth, create+light event, unknown trip 404 |
| test_throttle.py | 1 | 5 reroutes succeed, 6th returns 403 |
| test_payments.py | 5 | Plans public, webhook auth, RC upgrade, Stripe sig, expiry |
| test_scheduler.py | 3 | Unreachable-lock conflict, feasible preserves times, skipped excluded |
| test_embedding.py | 2 | Synthetic determinism + normalized, cosine self-similarity |

---

## 11. IMPLEMENTATION HISTORY

| Fix | Commit | What Changed |
|-----|--------|--------------|
| #1 Auth/IDOR | `fix(security)` | Added security.py, JWT verify + dev fallback, trip ownership, removed /user/{id}/upgrade |
| #2 Payments | `fix(payments)` | Wired payment_router into main.py, 6 auth-gated endpoints, webhooks fail-closed |
| #3 Real AI | `feat(ai)` | Auto-detect real vs synthetic embeddings, async state machine, LLM wired into loop |
| #4 Scheduler | `feat(scheduler)` | Transit-aware rescheduling, circuit breaker with candidate rotation, opening_hours on TripNode |
| #5 Tests + SQL | `feat(tests)` | Real pytest suite (20 tests), fixed $$ dollar-quoting, Supabase parity (off by default) |
| #5b Settings | `fix(settings)` | Restored supabase_jwt_secret + jwt_audience lost during edit race |
| #5c SQL $$ | `fix(sql)` | Final pass: confirmed all 5 PL/pgSQL functions have valid $$ delimiters |

---

## 12. REMAINING WORK

### Next Phase: Keys & Live Integration
| Task | Priority | Notes |
|------|----------|-------|
| Configure TB_LITELLM_API_KEY (OpenAI) | HIGH | Enables real GPT-4o + embeddings |
| Configure TB_GEMINI_API_KEY | HIGH | Enables Gemini Flash light model |
| Set up Supabase project + run schema SQL | HIGH | Enables real persistence + real auth |
| Tighten CORS (remove allow_origins=["*"]) | MEDIUM | Security hardening for production |
| Replace datetime.utcnow() with datetime.now(UTC) | LOW | Deprecation warnings (cosmetic) |
| Add weather_alert / change_mood auto-swap | LOW | Currently informational only |

### Future Phases
| Task | Owner | Priority |
|------|-------|----------|
| Flutter mobile app | Coding Agent | HIGH |
| UX/UI Design (Figma) | Human Designer | HIGH |
| Security audit | Human Security Eng | MEDIUM |
| Legal (Privacy Policy, ToS) | Lawyer | MEDIUM |
| Play Store listing + ASO | Human | MEDIUM |
| Venue partnerships (Dubai) | Business Dev | LOW (post-launch) |
| Load testing (k6) | Either | LOW |

---

## 13. QUICK START (For Any Developer/Agent)

```bash
# 1. Clone
git clone https://github.com/vneogi/travel-buddy.git
cd travel-buddy

# 2. Install
pip install -r requirements.txt

# 3. Run tests (no external deps needed)
pytest -q
# -> 20 passed in 0.42s

# 4. Run server with synthetic data
python main.py
# -> http://localhost:8000/docs

# 5. Test an endpoint (dev-mode auth)
curl -H "X-Debug-User-Id: test-user-1" http://localhost:8000/api/v1/user/status

# 6. For production: fill .env from .env.example, then:
docker-compose up -d
```

---

## 14. PERSISTENCE BACKEND SWITCHING

The app defaults to **in-memory** (no external deps). To switch to Supabase:

1. Set `TB_SUPABASE_URL`, `TB_SUPABASE_KEY`, `TB_SUPABASE_JWT_SECRET` in .env
2. Run the SQL from `models/database.py` (`SCHEMA_SQL`) against your Supabase database
3. Run the SQL from `services/supabase_service.py` (`ADDITIONAL_SQL_FUNCTIONS`)
4. Change imports in `routers/trip_router.py`, `routers/payment_router.py`, `agents/state_machine.py`:
   - FROM: `from services.database_service import db_service`
   - TO: `from services.db_provider import db as db_service`
5. Test with a live integration test before going to production

---

*Last updated: August 3, 2026*
*Built by: Vikrant Neogi + Genie Code*
*Version: 3.0 (post fixes #1–#5, all tests green)*
