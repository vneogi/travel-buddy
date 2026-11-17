# Travel Buddy

Travel Buddy is an on-trip companion for the **independent trip captain**: the
person holding the bookings and deciding what happens next when the day
changes. It keeps one trip spine (bookings, hotels, must-dos and deliberate
gaps) and helps in the moment: what to do now, how to recover when a stop falls
through, how to get a driver to the right place, and what still works without
signal. Every change to the plan is proposed, explained and confirmed by the
traveller. Nothing reflows silently.

A FastAPI backend (Cloud Run, Supabase Postgres with pgvector) and a Flutter
Android client. Product detail lives in `docs/VISION.md` section 0; build
status lives in `docs/PROJECT_STATUS.md`.

## Who it is for

- **Primary user:** the independent trip captain -- solo, paired, or
  coordinating a family -- in emerging and non-Western destinations.
- **Seeding beachhead:** budget backpackers on the South-East Asian overland
  corridor, where distribution and on-trip signal are dense.
- **Monetization hypothesis:** the Indian outbound traveller corridor (Dubai,
  Bangkok, Singapore, Baku, Tbilisi, Almaty). Under-evidenced; revisited with
  field data.

Owner documents: `docs/MARKET_STRATEGY.md` and `docs/VISION.md` section 3.

## What it does today (on `main`)

**Plan the spine**
- Guided Create Trip (destination, dates, party, interests) from a curated
  catalog, including a multi-city Laos corridor.
- Bookings as locked anchors (flight, hotel, tour), with provider-aware paste
  import and destination-local times.
- Flexible trip spans with empty days; typed Add, Move and Swap, each checked
  server-side against opening hours, walking reachability and locked bookings.

**Decide on the day**
- Date-scoped itinerary with a NOW / UP NEXT strip, and a Home "Now / Up next"
  card.
- One persistent, trip-scoped Ask. What Now returns feasible options for the
  time, energy, walking and intent you choose, with reasons and named unknowns;
  one-tap situation chips (quick break, low energy, indoors, something to eat).
- Swap with honest refusal reasons when nothing fits; visited / skipped
  outcomes; weather and departure alerts that never change the plan on their
  own.

**Get there**
- Offline Driver Card with local-script names and provenance tiers (sourced,
  ask to confirm, or refused), a full-screen Show-to-driver mode, and a Maps
  hand-off.

**Keep working offline**
- Cached itinerary and driver cards, an honest "saved on this phone" status
  row, and a signal outbox that syncs when the network returns.

**Trust and privacy**
- No dietary suitability claims; sponsored results are always labelled.
- Anonymous JWT identity, encrypted on-device database, server-side ownership
  checks, and erase / export routes (SPEC-43 foundation).

In progress behind CI: inspectable swap comparison (SPEC-50) and a
network-reachability provider (flag off by default).

## Where it works

Curated catalogs are loaded for Laos (Luang Prabang, Vang Vieng, Vientiane),
Tanzania (Stone Town and Nungwi) and Dubai (demo). Adding a city is still a
code and data change until the region registry and city kit exist
(SPEC-13, SPEC-20).

## What makes it different

- **On-trip, not pre-trip.** It owns the moment the plan breaks, not
  inspiration or booking.
- **Feasibility first.** Deterministic rules for hours, reachability and
  locked bookings decide what is possible; models may explain, never decide.
- **The traveller confirms every change.** No silent autonomous reflow.
- **Offline is a feature.** The trip, driver cards and status work with no
  signal.
- **Sourced facts and named uncertainty.** "Not available" instead of a
  guess; local names carry their source.
- **Decision-outcome data as the long-run moat.** Foundations are built; it
  becomes a moat only with retained real-world use (`docs/VISION.md`
  section 4).

| Read this | For |
|-----------|-----|
| `docs/DOCUMENT_MAP.md` | How to resume; which document owns which question |
| `docs/PROJECT_STATUS.md` | What is built, what is next, known risks |
| `docs/HOSTED_STATE.md` | Hosted migrations and credential-backed provider verification |
| `docs/ENGINEERING_RULES.md` | Rules earned from real bugs. Read before contributing |
| `docs/VISION.md` | Product at a glance (section 0), strategy and the data moat thesis |
| `docs/MARKET_STRATEGY.md` | Which traveller, which cities, Banana Pancake seeding order |
| `docs/RELEASE_READINESS.md` | Owner field test vs first non-owner vs public store |
| `docs/AWAITING_VERIFICATION.md` | Dated log of what is not yet verified on device |
| `docs/specs/SPEC-37-phone-field-test-delivery.md` | Hosted, installable, phone-independent field-test gate |
| `docs/DATA_LAYER_ROADMAP.md` | Schema and data-layer sequence |
| `docs/DATA_FLYWHEEL_OPERATING_MODEL.md` | How consented trip evidence becomes reviewed claims |
| `docs/specs/` | Numbered specifications, SPEC-01 onward |

## Architecture

    Flutter app (mobile/)
      SignalService -> SQLite outbox -> SyncEngine -> POST /api/v1/signals
      ApiClient (Dio, typed exception hierarchy)
      Riverpod controllers, offline-first cache

    FastAPI backend
      routers/trip_router.py      trip CRUD, events, reroutes, guardrails
      routers/signal_router.py    behavioural signal ingest (batch, idempotent)
      routers/debug_router.py     error ring buffer, debug builds only
      routers/payment_router.py   RevenueCat webhooks (optional import)
      agents/state_machine.py     sequential orchestration pipeline
      agents/router_agent.py      intent classifier and model router
      services/db_provider.py     resolves in-memory vs Supabase at import
      services/scheduler.py       opening hours, transit, locked nodes
      services/cache_service.py   semantic cache
      monitoring/error_log.py     request IDs and traceback capture

    Supabase (PostgreSQL + pgvector)
      supabase/migrations/0001 .. 0027 (hosted state in docs/HOSTED_STATE.md)

The orchestrator is **not** LangGraph, despite what older revisions of this file
and the BRD claimed. `langgraph` is commented out in `requirements.txt` and the
`GraphState` TypedDict is unused. `agents/state_machine.py` runs a hand-rolled
sequence:

    classify_intent -> check_cache -> venue_search -> apply_structural -> generate_response

`weather_service`, `cost_tracker` and `rag_ingestion` exist as scaffolding and
are not wired into the request path.

## Persistence

`services/db_provider.py` picks the backend at import time: Supabase when
`TB_SUPABASE_URL` and the service key are present, in-memory otherwise.
In-memory state resets on restart and is not shared across processes, so it is
for tests and quick local work only.

`DatabaseService` and `SupabaseService` are independent implementations of one
interface. `tests/test_backend_parity.py` fails if their signatures diverge,
because that divergence has crashed startup before (R13). A green suite against
in-memory proves nothing about the Supabase path (R4).

## Cost-control guardrails

| Lever | Name | Implementation |
|-------|------|----------------|
| 1 | Reroute throttle | Free users 5 reroutes/day, Pro 50/day |
| 2 | Semantic cache | Cosine similarity above 0.92 serves a cached response at zero LLM cost |
| 3 | Circuit breaker | At most 3 internal transitions before falling back |
| 4 | Asymmetric router | Light model for info queries, heavy model for restructuring |
| 5 | Ad-injection boost | Sponsored venues receive a score boost in RAG results; the UI always labels boosted results (SPEC-17) |

All five levers are configured in `config/settings.py`.

## Quick start

    pip install -r requirements.txt
    cp .env.example .env          # Supabase and OpenAI creds, optional for in-memory
    uvicorn main:app --reload --port 8000

Then open http://localhost:8000/docs

For local development without Supabase Auth, set `TB_DEBUG=true` and send an
`X-Debug-User-Id` header with a real UUID. Never run that way anywhere reachable
from the internet -- one header impersonates any user.

## API

`/docs` is the contract. It is generated from the code, so it cannot go stale;
a table here would (R16). The routes cluster as `/api/v1/health`,
`/api/v1/trip/*`, `/api/v1/signals`, `/api/v1/venues/search` and
`/api/v1/debug/*`.

Example event:

    POST /api/v1/trip/event
    {
      "user_id": "user-123",
      "trip_id": "<from trip/create>",
      "event_type": "swap_activity",
      "message": "I'm too tired for the gallery walk, find me a quiet cafe",
      "target_node_id": "<node to replace>",
      "preferences": {"vibe_tags": ["leisurely"], "mood": "relaxed"}
    }

## Project layout

    main.py                     FastAPI entry point
    seed_data.py                Dubai seed venues
    config/                     settings, regions, dietary vocabularies
    models/                     Pydantic schemas, signal type registry
    services/                   persistence, embeddings, cache, scheduler, maps
    agents/                     orchestration pipeline and intent router
    routers/                    HTTP layer
    monitoring/                 error ring buffer
    scripts/                    venue and glossary loaders, dev and smoke scripts
    supabase/migrations/        versioned SQL
    data/                       curated venue and dish datasets
    tests/                      pytest suite
    mobile/                     Flutter client
    docs/                       status, rules, vision, specs

## Tests

    pytest -q -ra

`-ra` prints a reason for every skip. A skip asserts nothing, so treat an
unexplained skip as a failure (R8). Flutter: `cd mobile && flutter analyze && flutter test`.

See `docs/TESTING_GUIDE.md` for the full playbook, including the airplane-mode
durability drill that gates the Laos field test. Final phone acceptance must use
an installed build and hosted API, not `flutter run`, a laptop LAN server, or
`adb reverse`; see SPEC-37.

## Status

`docs/PROJECT_STATUS.md` is the single source of truth for what works, what is
next and what is broken. This file deliberately does not duplicate it.
