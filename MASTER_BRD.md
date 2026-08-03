# TRAVEL BUDDY AI - MASTER BRD & TECHNICAL SPECIFICATION
## Version 2.0 | August 2026 | Dubai MVP

> **Purpose**: This is the single source of truth for the entire Travel Buddy project.
> Any AI coding agent, developer, or platform can ingest this document to resume work instantly.

---

## 1. PROJECT OVERVIEW

**What**: AI-powered travel companion backend with a continuous, self-correcting itinerary state loop.

**Core Problem**: Standard AI itineraries are static. When context changes (fatigue, weather, mood), regenerating breaks the timeline and erases locked reservations.

**Solution**: A state machine that maintains a live itinerary in memory, accepts real-time interruptions, intelligently replaces activities via RAG, and shifts the schedule while preserving locked items.

**Geo-fence**: Dubai, UAE (MVP). Expand globally after validation.

**Target**: Play Store deployment (Android first, iOS to follow).

---

## 2. WHAT'S ALREADY BUILT (Full Inventory)

### 2.1 Project Structure

```
travel-buddy-mvp/
├── main.py                          # FastAPI entry point
├── seed_data.py                     # 16 curated Dubai venues (synthetic)
├── requirements.txt                 # MVP dependencies
├── requirements-prod.txt            # Full production dependencies
├── Dockerfile.py                    # Multi-stage production container
├── docker-compose.yml               # Local dev stack (app + pgvector + redis)
├── .env.example                     # All required environment variables
├── MASTER_BRD.md                    # THIS FILE
├── README.md                        # Quick start guide
│
├── config/
│   └── settings.py                  # All guardrail levers + env config
│
├── models/
│   ├── schemas.py                   # Pydantic models, TripState, TypedDicts
│   └── database.py                  # Full PostgreSQL + pgvector schema SQL
│
├── services/
│   ├── database_service.py          # In-memory DB (MVP testing)
│   ├── supabase_service.py          # PRODUCTION: Real Supabase + pgvector
│   ├── embedding_service.py         # Vector embedding (synthetic + real)
│   ├── llm_service.py               # PRODUCTION: LiteLLM gateway, routing, cost tracking
│   ├── cache_service.py             # Semantic cache (Lever 2)
│   ├── maps_service.py              # Mock Google Maps (MVP testing)
│   ├── google_maps_real.py          # PRODUCTION: Real Distance Matrix + Places
│   ├── weather_service.py           # PRODUCTION: OpenWeatherMap + alerts
│   └── payment_service.py           # PRODUCTION: RevenueCat + Stripe
│
├── agents/
│   ├── state_machine.py             # LangGraph state loop (5 nodes)
│   └── router_agent.py              # Intent classifier + model router
│
├── routers/
│   ├── trip_router.py               # Trip CRUD + event processing + guardrails
│   └── payment_router.py            # Subscription management endpoints
│
├── pipeline/
│   ├── chunker.py                   # Semantic chunking (venue-aware)
│   └── rag_ingestion.py             # Full scrape->chunk->embed->store pipeline
│
├── monitoring/
│   └── cost_tracker.py              # LLM cost tracking + budget alerts
│
└── .github/workflows/
    └── ci.yml                       # Lint -> Test -> Build -> Deploy
```

### 2.2 Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI app + routing | COMPLETE | All endpoints working, tested with TestClient |
| State machine (5 nodes) | COMPLETE | classify -> cache -> search -> respond -> update |
| Guardrail Lever 1 (throttle) | COMPLETE | Blocks at limit with 403 + upgrade prompt |
| Guardrail Lever 2 (cache) | COMPLETE | Cosine similarity 0.92 threshold |
| Guardrail Lever 3 (breaker) | COMPLETE | Max 3 loops, deterministic fallback |
| Guardrail Lever 4 (routing) | COMPLETE | Light/heavy classification |
| Guardrail Lever 5 (ads) | COMPLETE | Sponsored boost in hybrid search |
| Venue seed data (16) | COMPLETE | Curated Dubai venues with coordinates |
| Supabase service | COMPLETE | Real client code, awaits credentials |
| LLM service (LiteLLM) | COMPLETE | GPT-4o + Gemini Flash + fallbacks + streaming |
| Weather service | COMPLETE | OpenWeatherMap + Dubai-specific alerts |
| Google Maps (real) | COMPLETE | Distance Matrix + Places (New) API |
| Payment service | COMPLETE | RevenueCat (mobile) + Stripe (web) |
| RAG pipeline | COMPLETE | TimeOut + Reddit scrapers + semantic chunking |
| Cost monitoring | COMPLETE | Per-user attribution + budget alerts |
| Docker deployment | COMPLETE | Multi-stage build + docker-compose |
| CI/CD (GitHub Actions) | COMPLETE | Lint -> Test -> Build -> Deploy to Railway |

---

## 3. ARCHITECTURE

### 3.1 Request Flow

```
Mobile App (Flutter)
    │
    ▼
[FastAPI Router] ─── Lever 1: Check reroute quota
    │
    ▼
[State Machine]
    ├─ Node 1: Classify Intent (Lever 4: light vs heavy)
    ├─ Node 2: Check Semantic Cache (Lever 2)
    ├─ Node 3: Hybrid Venue Search (Lever 5: sponsored boost)
    ├─ Node 4: Generate Response (Lever 3: circuit breaker)
    └─ Node 5: Update Trip State
    │
    ▼
[Supabase PostgreSQL + pgvector]
```

### 3.2 Model Routing

| Intent Type | Model | Cost/1K tokens | Use Case |
|-------------|-------|----------------|----------|
| Structural (reroute, swap) | GPT-4o | $0.0025 in / $0.01 out | Itinerary rewrites |
| Informational (translate, info) | Gemini 1.5 Flash | $0.000075 in / $0.0003 out | Simple QA |
| Embedding | text-embedding-3-small | $0.00002 | Vector search |

---

## 4. API CONTRACT

### Endpoints

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/api/v1/health` | Health + system stats |
| POST | `/api/v1/trip/create` | Create Dubai itinerary |
| GET | `/api/v1/trip/{trip_id}` | Get trip state |
| POST | `/api/v1/trip/event` | **Main endpoint** - process events |
| GET | `/api/v1/user/{user_id}/status` | Tier + reroute info |
| POST | `/api/v1/user/{user_id}/upgrade` | Upgrade to Pro |
| GET | `/api/v1/venues/search` | RAG venue search |
| GET | `/api/v1/stats` | System analytics |
| GET | `/api/v1/payment/plans` | Available plans |
| POST | `/api/v1/payment/checkout` | Stripe checkout |
| POST | `/api/v1/payment/verify-purchase` | Mobile IAP verify |
| POST | `/api/v1/payment/webhook/stripe` | Stripe events |
| POST | `/api/v1/payment/webhook/revenuecat` | RevenueCat events |

### Main Event Request (POST /api/v1/trip/event)

```json
{
  "user_id": "string",
  "trip_id": "uuid",
  "event_type": "cancel_activity|swap_activity|add_activity|change_mood|weather_alert|translate|ask_info|reroute",
  "message": "natural language input",
  "target_node_id": "optional - node to modify",
  "preferences": {"vibe_tags": [], "mood": "", "audience": []}
}
```

---

## 5. DATABASE SCHEMA

Full SQL in `models/database.py`. Key tables:

- **user_tiers**: user_id, tier_status, daily_reroute_count, max_daily_reroutes
- **trip_states**: trip_id, user_id, state_json (JSONB), is_active
- **venues_rag**: name, description, lat/lng, vibe_tags[], embedding VECTOR(1536), is_sponsored, bid_weight
- **cached_responses**: query_embedding VECTOR(1536), cached_response_text, expires_at
- **event_log**: user_id, event_type, routing_tier, from_cache, token_cost_estimate

Custom SQL functions: `hybrid_venue_search()`, `check_semantic_cache()`, `increment_reroute()`, `reset_daily_reroutes()`

---

## 6. ENVIRONMENT VARIABLES REQUIRED

See `.env.example` for full list. Critical ones:

```
TB_SUPABASE_URL, TB_SUPABASE_KEY
TB_LITELLM_API_KEY (OpenAI key)
GEMINI_API_KEY
TB_GOOGLE_MAPS_API_KEY
TB_OPENWEATHER_API_KEY
TB_STRIPE_SECRET_KEY, TB_STRIPE_WEBHOOK_SECRET
TB_REVENUECAT_API_KEY
```

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

## 10. REMAINING WORK (Human/External Required)

| Task | Owner | Priority |
|------|-------|----------|
| UX/UI Design (Figma) | Human Designer | HIGH |
| Flutter mobile app | Coding Agent (Cursor) | HIGH |
| Security audit | Human Security Eng | MEDIUM |
| Legal (Privacy Policy, ToS) | Lawyer | MEDIUM |
| Play Store listing + ASO | Human | MEDIUM |
| Venue partnerships (Dubai) | Business Dev | LOW (post-launch) |
| Load testing (k6) | Either | LOW |
| Accessibility audit | Human QA | LOW |

---

## 11. QUICK START (For Any Developer/Agent)

```bash
# 1. Clone and install
cd travel-buddy-mvp
pip install -r requirements.txt

# 2. Run with synthetic data (no external deps needed)
python main.py
# -> http://localhost:8000/docs

# 3. Run tests
pytest tests/ -v

# 4. For production: fill .env from .env.example, then:
docker-compose up -d
```

---

*Last updated: August 3, 2026*
*Built by: Vikrant Neogi + Genie Code*
