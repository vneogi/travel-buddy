# Travel Buddy

An AI travel companion: a FastAPI backend and a Flutter client that together
maintain a continuous, self-correcting itinerary. The traveller interrupts the
plan ("too tired for the gallery walk, find me a quiet cafe"), the system
replaces the affected activity using curated local venue knowledge (RAG), and
reschedules everything downstream without moving locked reservations.

Two regions are loaded: Dubai (16 synthetic venues) and Laos (58 hand-curated
venues across Luang Prabang, Vang Vieng and Vientiane) for a field test on
Oct 2 2026.

| Read this | For |
|-----------|-----|
| `docs/PROJECT_STATUS.md` | What is built, what is next, known risks |
| `docs/ENGINEERING_RULES.md` | Rules earned from real bugs. Read before contributing |
| `docs/VISION.md` | Product strategy and the data moat thesis |
| `docs/AWAITING_VERIFICATION.md` | Dated log of what is not yet verified on device |
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
      supabase/migrations/0001 .. 0010

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
| 5 | Ad-injection boost | Sponsored venues receive a score boost in RAG results |

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
durability drill that gates the Laos field test.

## Status

`docs/PROJECT_STATUS.md` is the single source of truth for what works, what is
next and what is broken. This file deliberately does not duplicate it.
