> Product vision and strategy live in [docs/VISION.md](docs/VISION.md).
> This document is the technical specification.

# TRAVEL BUDDY -- MASTER BRD AND TECHNICAL SPECIFICATION

## Version 5.0

> This document describes how the system is designed to work. It deliberately
> records no status, no test counts and no commit history, because every earlier
> revision that tried to do so was wrong within days (R16).
>
> - Current state, priorities and known risks: `docs/PROJECT_STATUS.md`
> - Unverified work and open defects: `docs/AWAITING_VERIFICATION.md`
> - Rules earned from real bugs: `docs/ENGINEERING_RULES.md`
> - Repository layout: `README.md`

---

## 1. Project overview

**What:** an AI travel companion with a continuous, self-correcting itinerary
state loop.

**Core problem:** AI itineraries are static. When context changes -- fatigue,
weather, a closed venue, a mood shift -- regenerating the plan destroys the
timeline and erases locked reservations.

**Solution:** hold a live itinerary as state, accept real-time interruptions,
replace only the affected activity using curated local venue knowledge, and
reschedule what follows while preserving anything locked.

**Regions:** Dubai (16 synthetic venues) and Laos across Luang Prabang, Vang
Vieng and Vientiane (58 hand-curated venues). `geo_region` is per trip, set from
`settings.geo_fence` at creation, which is what makes multi-city possible.

**Near-term goal:** a real field test in Laos on Oct 2 2026. That date is the
forcing function for everything prioritized in `docs/PROJECT_STATUS.md`.

**Target platform:** Android first via the Play Store, iOS to follow.

**Repository:** `github.com/vneogi/travel-buddy`, branch `main`.

---

## 2. Architecture

### 2.1 Request flow

    Flutter app
        |
        v
    FastAPI router
        |    Auth: JWT verification, or X-Debug-User-Id only when no secret is set
        |    Lever 1: atomic consume_reroute() before any work is done
        v
    Orchestration pipeline (agents/state_machine.py)
        |-- classify_intent        Lever 4: light vs heavy model
        |-- check_cache            Lever 2: semantic cache
        |-- venue_search           Lever 5: sponsored boost in hybrid RAG
        |-- apply_structural       Lever 3: circuit breaker, 3 attempts
        |     `-- scheduler: transit-aware, respects locked anchors and hours
        `-- generate_response and update trip state
        |
        v
    Supabase (PostgreSQL + pgvector), or in-memory when no credentials

### 2.2 The orchestrator is not LangGraph

Earlier revisions of this document and the README described an "async LangGraph
loop". That is false and has misled several agents. `langgraph` is commented out
in `requirements.txt`, the `GraphState` TypedDict is unused, and
`agents/state_machine.py` is a hand-rolled sequential pipeline. Adopting a graph
framework is a legitimate future choice, but it must not be documented as though
it already happened.

### 2.3 Model routing

| Intent type | Model | Cost per 1K tokens | Use case |
|-------------|-------|--------------------|----------|
| Structural (reroute, swap, cancel, add) | gpt-4o | 0.0025 in / 0.01 out | Itinerary rewrites |
| Informational (translate, info) | gpt-4o-mini | 0.00015 in / 0.0006 out | Simple QA, ~16x cheaper |
| Embedding | text-embedding-3-small | 0.00002 | Vector search |

Fallback chains:

- LIGHT: `["gpt-4o-mini"]`. Gemini was removed after a key-type and VertexAI
  routing problem.
- HEAVY: `["gpt-4o", "claude-3-5-sonnet-20241022", "gemini/gemini-1.5-pro"]`

All traffic goes through the LiteLLM gateway in `services/llm_service.py`.

---

## 3. Persistence

`services/db_provider.py` resolves the backend once, at import time: Supabase
when `TB_SUPABASE_URL` and the key are present, in-memory otherwise. Callers
import `db_service` from `db_provider` and never from a concrete backend.

There is no manual flip to perform. Earlier revisions of this document
instructed the reader to swap three imports to enable Supabase; that work is
done and the instructions were actively harmful.

`DatabaseService` (in-memory) and `SupabaseService` are independent
implementations of one contract. Two consequences, both learned the hard way:

- A green suite against in-memory proves nothing about the Supabase path.
  Any change touching persistence changes both backends, and any new table
  ships its migration in the same commit (R4).
- Divergence surfaces only at runtime. `record_signal` and
  `get_valid_signal_types` were each missing from `supabase_service`, and
  `add_venue` differed in arity, which crashed startup once the provider
  resolved to Supabase. `tests/test_backend_parity.py` now asserts signature
  compatibility (R13).

In-memory state resets on restart and is not shared across processes. The
startup log prints `supabase_configured` as a boolean, which is the only
reliable way to know which backend you are talking to. An API success response
is not proof of persistence -- the sync engine once reported `accepted=1` for
five signals that were all discarded on restart (R11).

---

## 4. Auth contract

- Every endpoint requires auth except `GET /`, `GET /api/v1/health` and
  `GET /api/v1/payment/plans`.
- Production: `Authorization: Bearer <supabase_jwt>`, verified HS256 against
  `TB_SUPABASE_JWT_SECRET`.
- Local development, only when `TB_DEBUG=true` **and** no JWT secret is
  configured: `X-Debug-User-Id: <uuid>`.
- When a JWT secret is configured the debug header is ignored. This ordering is
  load-bearing; see section 10.
- `user_id` in a request body is optional and ignored. Identity comes from the
  token or header only.
- Trip endpoints enforce ownership. Requesting another user's trip returns 403.

The shared `TB_DEBUG_USER_ID` used by tester builds is not an identity system.
SPEC-09 replaces it with a per-device UUID, and no build should be distributed
to testers before that lands.

---

## 5. API contract

`/docs` is generated from the code and is the authoritative contract. The table
below is a map, not a source of truth.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | Public | App info |
| GET | `/api/v1/health` | Public | Health, venue count, cache stats |
| GET | `/api/v1/user/status` | Required | Tier and remaining reroutes |
| POST | `/api/v1/trip/create` | Required | Create an itinerary, with party context |
| GET | `/api/v1/trip/{trip_id}` | Required, owner | Trip state plus party |
| POST | `/api/v1/trip/event` | Required, owner | Main endpoint: process an event |
| GET | `/api/v1/venues/search` | Required | Hybrid RAG venue search |
| GET | `/api/v1/stats` | Required | Cache, event and venue analytics |
| POST | `/api/v1/signals` | Required | Behavioural signal ingest, batch |
| GET | `/api/v1/debug/errors` | Required, debug only | Error ring buffer, 404 in production |
| GET | `/api/v1/payment/plans` | Public | Subscription plans |
| GET | `/api/v1/payment/status` | Required | Subscription status |
| POST | `/api/v1/payment/checkout` | Required | Stripe checkout session |
| POST | `/api/v1/payment/verify-purchase` | Required | RevenueCat IAP verification |
| POST | `/api/v1/payment/webhook/stripe` | Signature | Stripe webhooks |
| POST | `/api/v1/payment/webhook/revenuecat` | Auth header | RevenueCat webhooks |

`POST /api/v1/user/{user_id}/upgrade` was deleted from the code. It granted Pro
with no payment and no auth. Tier changes happen only through verified payments.

### Main event request

    POST /api/v1/trip/event
    {
      "trip_id": "uuid",
      "event_type": "cancel_activity|swap_activity|add_activity|change_mood|weather_alert|translate|ask_info|reroute",
      "message": "natural language input",
      "target_node_id": "optional, node to modify",
      "preferences": {"vibe_tags": [], "mood": "", "audience": []}
    }

### Event classification

| Category | Events | Model |
|----------|--------|-------|
| Structural, venue required | swap_activity, add_activity, reroute | Heavy |
| Structural, no venue | cancel_activity | Heavy |
| Informational | ask_info, translate, change_mood, weather_alert | Light |

Quota note: `change_mood` and `weather_alert` are classified informational for
model routing but still consume reroute quota, because they can restructure the
itinerary.

---

## 6. Behavioural signals

Signals are the product's actual asset. Everything else is a means of collecting
them: what the traveller accepted, rejected, skipped, loved, or arrived late to.

- `models/signal_types.py` is the single registry of signal types, their
  `value_kind`, and their payload shapes. A drift guard test fails if the
  registry and its consumers disagree. Never mirror this list anywhere (R5).
- `POST /api/v1/signals` ingests batches idempotently, rejects per item rather
  than per batch, and tolerates clock skew on `captured_at`.
- The client never blocks on the network. `SignalService` writes to a SQLite
  outbox first, and `SyncEngine` drains it with single-flight batching and
  exponential backoff. It recovers in-flight rows on startup after a crash.
- Some signals are server-derived rather than client-sent. `arrival_delta` is
  computed from `visited_confirmed.captured_at` against `node.scheduled_start`,
  so one tap yields two data points. Derivation is idempotent and never blocks
  ingest.
- A schema that cannot express a fact will never complain. Dish-level
  observations were not unsupported, they were unrepresentable, and missing data
  looked exactly like absent behaviour. Prefer generalizing a subject reference
  (`entity_type` plus `entity_id`) over adding a table per subject (R9).

---

## 7. Database schema

Versioned SQL lives in `supabase/migrations/`, applied in numeric order.
`models/database.py` holds the original schema SQL. Core tables:

- **user_tiers**: user_id, tier_status, daily_reroute_count, max_daily_reroutes,
  last_reset_date
- **trip_states**: trip_id, user_id, state_json (JSONB), is_active
- **trip_party** and party members: party type and size, stamped server-side
- **venues_rag**: name, description, lat, lng, vibe_tags[], audience[],
  category, micro_location, opening_hours_structured (JSONB), geo_region,
  is_sponsored, bid_weight, embedding VECTOR(1536)
- **venue_dish** and **dish_glossary**: dish_key, name_en, name_local,
  name_roman, cuisine, allergens, dietary labels
- **signal**, **signal_type**, **source**: behavioural capture
- **cached_responses**: query_embedding VECTOR(1536), cached_response_text,
  expires_at, hit_count
- **event_log**: user_id, event_type, routing_tier, from_cache,
  token_cost_estimate

SQL functions:

| Function | Purpose |
|----------|---------|
| `reset_daily_reroutes()` | Cron, resets all counters at midnight |
| `hybrid_venue_search(...)` | pgvector cosine plus distance filter plus sponsored boost |
| `increment_reroute(user_id)` | Atomic increment, retained for compatibility |
| `consume_reroute(user_id)` | Atomic check-and-increment, used by the throttle |
| `check_semantic_cache(...)` | Vector similarity search over the cache table |

**Known drift.** `scripts/load_venues.py` writes `typical_dwell_minutes`,
`indoor_outdoor` and `price_band` to `venues_rag`, and no migration defines
those columns. `name_local` and `nearest_landmark` are also absent, which blocks
driver cards. A database rebuilt from `supabase/migrations/` today fails on
load. `supabase_service` also passes a `geo_region` filter that the RPC in
`0001_initial_schema.sql` does not declare. Both are tracked in
`docs/AWAITING_VERIFICATION.md`.

---

## 8. Environment variables

All are prefixed `TB_`. See `.env.example` for the full list.

    # Database
    TB_SUPABASE_URL=              # Supabase project URL
    TB_SUPABASE_KEY=              # service role key

    # Auth
    TB_SUPABASE_JWT_SECRET=       # HS256 verification secret
    TB_DEBUG=false                # defaults to false, fail-closed

    # Models
    TB_LITELLM_API_KEY=           # OpenAI key: gpt-4o, gpt-4o-mini, embeddings
    TB_LLM_DEBUG=false            # opt-in verbose LLM logging, see R12

    # CORS
    TB_CORS_ALLOWED_ORIGINS=*     # comma-separated in production

    # External APIs
    TB_GOOGLE_MAPS_API_KEY=
    TB_OPENWEATHER_API_KEY=

    # Payments
    TB_STRIPE_SECRET_KEY=
    TB_STRIPE_WEBHOOK_SECRET=
    TB_STRIPE_PRICE_MONTHLY=
    TB_STRIPE_PRICE_YEARLY=
    TB_REVENUECAT_API_KEY=
    TB_REVENUECAT_WEBHOOK_AUTH=

`TB_DEBUG` must never be true on a deployment reachable from the internet. Which
keys are currently populated is environment state, not specification, so it is
not recorded here.

`TB_LLM_DEBUG` exists because raising the root log level for a debug flag once
dumped full request bodies, 1536-float embedding arrays and a masked
Authorization header to stdout. Raise your own loggers, never the root (R12).

The venue loader reads `TB_SUPABASE_KEY`. Some documentation has referred to
`TB_SUPABASE_SERVICE_KEY`; reconcile the names before trusting either.

---

## 9. Mobile application

### Stack

Flutter 3.x with Riverpod for state, GoRouter for navigation, Dio for HTTP,
`google_maps_flutter` for maps, Supabase Auth for identity, the RevenueCat
Flutter SDK for payments, `sqflite` for the offline outbox and cache, and
Firebase Cloud Messaging for push.

### Screens

1. Onboarding: mood selection and travel-style questions
2. Home and trip list
3. Live itinerary: timeline of draggable, lockable activity cards
4. Activity detail: venue info, swap, transit time
5. Swap sheet: RAG suggestions filtered by vibe
6. Map view: venue pins and transit polylines
7. Chat: natural language input
8. Profile: settings, tier, sync status
9. Upgrade: plan comparison and paywall

### UX invariants

- Locked activities show a padlock and cannot be swiped away.
- Weather alerts appear as a banner offering a one-tap indoor swap.
- Remaining reroutes appear as a counter badge.
- Cache hits must feel instant, with no spinner.
- Every accept, reject, skip and confirm emits a signal. A UI affordance that
  captures no signal is a missed observation and should be treated as a bug.

### Offline behaviour

Offline is the default assumption, not an error path. The traveller will be on a
foreign SIM in a tuk-tuk. Writes go to the outbox first and sync opportunistically
on app start, resume, connectivity regained, after each emit, and on a timer.

Any durability drill must first prove the failure mode is real. The first
airplane-mode test was meaningless because the build was talking to the laptop
over USB, which airplane mode does not disable (R7).

### Dart hazard

Writing `\$variable` instead of `$variable` inside a Dart string silently
produces a literal. It has broken the base URL, the Bearer token and a ValueKey
on three separate occasions. Grep after every Dart edit (R1).

---

## 10. Security

### The auth-bypass incident

A change moved the `X-Debug-User-Id` check ahead of JWT verification while
`debug` defaulted to true. Any client could impersonate any user with one
header. The entire test suite was green.

Root cause: the suite failed when a developer's `.env` contained
`TB_SUPABASE_JWT_SECRET`, which correctly enables JWT mode. The fix was applied
to the application's auth logic instead of to the test environment.

What closed it:

1. `security.py`: the JWT secret check always comes first. The debug header
   works only when no secret is configured.
2. `settings.py`: `debug` defaults to false.
3. `tests/conftest.py`: environment isolation, clearing the JWT secret before
   the app is imported.
4. `tests/test_auth.py`: a regression test proving `X-Debug-User-Id` returns 401
   when a secret is set.

The lesson generalizes beyond auth: never weaken production behaviour to satisfy
a failing test. When a test fails against real configuration, suspect the test
(R3).

### Other standing rules

- Webhooks fail closed. An unverifiable signature is a rejection.
- `/api/v1/debug/errors` returns 404 when debug is off.
- Error responses carry a `request_id` and nothing internal. Full tracebacks go
  to the log and the ring buffer.
- Startup logs booleans for credential presence, never values.
- Halal is not currently enforced against pork in the dietary checker. That is a
  safety defect, tracked as high severity, not a missing feature.

---

## 11. Deployment

### Railway, the default for now

Push to GitHub, connect Railway to the repository, set environment variables in
the dashboard with `TB_DEBUG=false`, and Railway builds from the Dockerfile on
push to `main`. CI runs Ruff, then tests, then build, then deploy.

### Docker Compose, local

    docker-compose up -d      # app, pgvector, redis
    open http://localhost:8000/docs

### Google Cloud Run

    gcloud run deploy travel-buddy --source . --region me-central1

---

## 12. Monetization

| Tier | Price | Includes |
|------|-------|----------|
| Free | 0 | 5 reroutes/day, light model, sponsored results |
| Pro monthly | 4.99/mo | 50 reroutes/day, heavy model, no sponsored results |
| Pro yearly | 39.99/yr | As monthly, two months free |

Revenue streams: subscriptions through RevenueCat and Stripe, sponsored venue
placement as a bounded score boost in RAG results, and affiliate booking links
later.

The sponsored boost is capped deliberately. A recommendation engine that can be
bought loses the trust that makes the signal data worth anything.

---

## 13. Testing

    pytest -q -ra

No expected counts are recorded here. `-ra` prints a reason for every skip, and
a skip asserts nothing: eight tests once silently degraded from passing to
skipped when `pytest-asyncio` vanished from an ephemeral environment, and the
summary still looked healthy (R8).

`tests/conftest.py` clears `TB_SUPABASE_JWT_SECRET`, `TB_SUPABASE_URL` and
`TB_SUPABASE_KEY` and sets `TB_DEBUG=true` before importing the app, so tests
run in dev-auth mode regardless of the developer's `.env`.

Tests must construct the same exception types production raises. A test that
threw `Exception('401 ...')` instead of `UnauthorizedException` is why a retry
bug survived a green suite (R3).

The full playbook, including the airplane-mode durability drill that gates the
Laos field test, is in `docs/TESTING_GUIDE.md`.

---

## 14. Where everything else lives

| Question | Answer |
|----------|--------|
| What is built and what is next | `docs/PROJECT_STATUS.md` |
| What is unverified or broken | `docs/AWAITING_VERIFICATION.md` |
| Why we are building it | `docs/VISION.md` |
| Signal and data-model design | `docs/DATA_MODEL_BRD.md` |
| Numbered specifications | `docs/specs/` |
| Rules from past bugs | `docs/ENGINEERING_RULES.md` |
| What changed and when | `git log` |

Built by Vikrant Neogi with AI coding agents.
