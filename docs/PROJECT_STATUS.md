# Travel Buddy — Project Status & Handoff

> Single source of truth for where the project stands and what remains.
> Last updated: 2026-08-05 (v7.0). Keep this file updated as milestones complete.

## 0. TL;DR

- **Backend**: functionally complete, hardened, **27 unit tests passing** + 5 skipped
  (Supabase integration). Signal capture endpoint live (`POST /signals`).
- **AI**: live via OpenAI (gpt-4o heavy, gpt-4o-mini light, text-embedding-3-small).
- **Supabase**: schema + functions deployed, signal tables ready (migration 0002).
  Venues NOT seeded. Backend still uses in-memory datastore (flip = 3 imports).
- **Flutter**: running end-to-end on Chrome + Android. 14 unit tests passing.
  Heart tap emits `user_loved` signal via `SignalService` seam.
- **Signal capture (SPEC-01)**: fully implemented — migration, server, Flutter, tests.
  Idempotent, auth-safe, both backends. Reviewed and gap-fixed (commit #38).
- **Offline queue (SPEC-02)**: spec written, NOT implemented. Awaiting review.
- **Migrations**: versioned tooling in place (`supabase/migrations/`). No more console SQL.

## 1. Commit History (all pushed to main)

| # | Message | Key files |
|---|---------|-----------|
| 1 | `feat: Initial Travel Buddy MVP` | Full backend scaffold |
| 2 | `fix(security): Add real auth + close IDOR holes` | security.py |
| 3 | `fix(payments): Wire payment router, close webhook holes` | routers/payment_router.py |
| 4 | `feat(ai): Auto-detect real vs synthetic AI, wire LLM` | agents/state_machine.py |
| 5 | `feat(tests): Real pytest suite + fix $$ SQL` | tests/ |
| 6 | `fix(settings): Restore missing auth fields` | config/settings.py |
| 7 | `fix(sql): Replace single $ with $$ dollar-quoting` | models/database.py |
| 8 | `docs: Update MASTER_BRD.md to v3.0` | MASTER_BRD.md |
| 9 | `fix(config): Switch light model to gpt-4o-mini` | config/settings.py |
| 10 | `fix(llm): Remove dead Gemini from LIGHT_FALLBACK` | agents/ |
| 11 | `feat: Supabase seeder, integration tests, CORS, throttle` | seed_supabase.py |
| 12 | `fix(ci): Add pyproject.toml for Ruff` | pyproject.toml |
| 13 | `security: Fix critical auth-bypass regression` | security.py |
| 14 | `docs: Update MASTER_BRD.md to v4.0` | MASTER_BRD.md |
| 15 | `docs: Add PROJECT_STATUS.md handoff document` | docs/ |
| 16 | `feat(mobile): Flutter app scaffold — full UI + integration` | mobile/ (31 files) |
| 17 | `fix(mobile): Correct Dart interpolation + API contract` | mobile/ (10 files) |
| 18 | `docs: Add comprehensive TESTING_GUIDE.md` | docs/ |
| 19 | `docs: Replace short TESTING_GUIDE.md with full version` | docs/ |
| 20 | `feat(mobile): Animated timeline reflow + StateNotifier` | 3 files |
| 21 | `fix(mobile): Replace AnimatedList with keyed ListView` | itinerary_screen.dart |
| 22 | `fix: Backend review — API key bug, memory leak, scope` | 6 files |
| 23 | `feat(tests): Flutter test suite + TESTING_GUIDE.md` | 5 files |
| 24 | `fix(weather): Syntax error — comment ate the colon` | weather_service.py |
| 25 | `fix(tests): autoDispose fix + mounted guards + fonts` | 3 files |
| 26 | `fix(mobile): Flutter 3.22 compat — CardThemeData` | 2 files |
| 27 | `fix(mobile): Guard tokenProvider against uninitialized Supabase` | providers.dart |
| 28 | `fix(mobile): Guard app_router redirect` | app_router.dart |
| 29 | `fix(mobile): ShimmerList overflow — Column to ListView` | shimmer_card.dart |
| 30 | `docs: Add VISION.md — product positioning, moat, strategy` | docs/VISION.md, MASTER_BRD.md |
| 31 | `docs: Add user research surveys (short + deep)` | docs/research/ |
| 32 | `docs: Extend VISION.md — capabilities matrix, audience, services` | docs/VISION.md |
| 33 | `docs: Extend DATA_MODEL_BRD.md §16 — audience + signals` | docs/DATA_MODEL_BRD.md |
| 34 | `docs: Add SPEC-01 — migration tooling + first signal slice` | docs/specs/ |
| 35 | `feat(migrations): SPEC-01 Part A — versioned migration tooling` | supabase/migrations/ |
| 36 | `feat(signals): SPEC-01 Part B — first signal slice (user_loved)` | 12 files |
| 37 | `docs: Add SPEC-02 — offline-first event queue + sync` | docs/specs/ |
| 38 | `fix(signals): Add record_signal to SupabaseService` | supabase_service.py |
| 39 | `fix: Replace datetime.utcnow() with timezone-aware` | 9 files |

## 2. Test Results

**Backend (pytest):** `27 passed, 5 skipped, 4 warnings`
- 5 skipped = Supabase integration tests (need live DB)
- 4 warnings = third-party (FastAPI on_event deprecation, HTTP_422 rename)
- 0 utcnow deprecation warnings (fixed in #39)

**Flutter:** `14 passed` (+ 4 signal tests = 18 expected after `flutter pub get`)
- models, repositories, itinerary controller, signal service

## 3. Architecture

```
Flutter App (mobile/)
  └─ SignalService (THE offline seam — SPEC-02 swaps here)
  └─ ApiClient (Dio + auth injection)
  └─ StateNotifier controllers (Riverpod)
       └─ POST /api/v1/signals (batch, idempotent)
       └─ POST /api/v1/trip/event
       └─ GET /api/v1/trip/{id}

FastAPI Backend
  ├─ routers/trip_router.py       (trip CRUD + events)
  ├─ routers/payment_router.py    (RevenueCat webhooks)
  ├─ routers/signal_router.py     (signal ingest — SPEC-01)
  ├─ security.py                  (JWT + debug auth)
  ├─ agents/state_machine.py      (LangGraph orchestrator)
  ├─ services/database_service.py (in-memory — active)
  ├─ services/supabase_service.py (production — ready, not flipped)
  └─ services/cache_service.py    (semantic cache)

Supabase (PostgreSQL + pgvector)
  ├─ 0001_initial_schema.sql      (5 tables, 5 functions)
  └─ 0002_signals_core.sql        (source, signal_type, signal)
```

## 4. Signal Capture (SPEC-01) — IMPLEMENTED

The first vertical slice of the data flywheel is live:
- **Migration 0002**: `source`, `signal_type`, `signal` tables with seeds
- **Server**: `POST /api/v1/signals` — batch, idempotent (client UUID = dedup key),
  auth from token (never body), consent stub seam, 422 on unknown types
- **Flutter**: `SignalService.emit()` → heart tap on ActivityCard → fire-and-forget
- **Both backends**: in-memory + Supabase have `record_signal()` + `get_valid_signal_types()`
- **Tests**: 6 pytest (idempotency proven) + 4 Flutter (wire format + error swallow)
- **Reviewer-identified gap fixed**: SupabaseService signal methods added (commit #38)

## 5. Scaffolded but NOT Wired (dead code — documented)

| Module | What it does | Why not wired |
|--------|-------------|---------------|
| `services/weather_service.py` | OpenWeather forecast | Needs `TB_OPENWEATHER_API_KEY` + route integration |
| `monitoring/cost_tracker.py` | LLM spend tracking | In-process only, needs persistence |
| `pipeline/rag_ingestion.py` | Venue embedding pipeline | Needs real embedding calls + Supabase |

## 6. Running Locally

**Backend:**
```bash
cd travel-buddy
pip install -r requirements.txt  # or: pip install fastapi uvicorn pydantic-settings litellm PyJWT httpx
export TB_DEBUG=true
# UNSET TB_SUPABASE_JWT_SECRET for debug auth
uvicorn main:app --reload --port 8000
# Tests: pytest -q (expect 27 passed, 5 skipped)
```

**Flutter:**
```bash
cd mobile
flutter pub get
flutter run -d chrome \
  --dart-define=TB_API_BASE_URL=http://localhost:8000 \
  --dart-define=TB_DEBUG_USER_ID=11111111-1111-1111-1111-111111111111
# Tests: flutter test (expect 18 passed)
# Android emulator: use http://10.0.2.2:8000 as API base
```

## 7. Environment Variables

| Variable | Purpose | Required? |
|----------|---------|-----------|
| `TB_DEBUG` | Enable debug auth (X-Debug-User-Id) | Dev only |
| `TB_LITELLM_API_KEY` | OpenAI API key for LLM routing | Yes (production) |
| `TB_SUPABASE_URL` | Supabase project URL | For Supabase backend |
| `TB_SUPABASE_KEY` | Supabase service role key | For Supabase backend |
| `TB_SUPABASE_JWT_SECRET` | JWT verification (MUST be unset for debug) | Production only |
| `TB_OPENWEATHER_API_KEY` | OpenWeather API key | weather_service only |
| `TB_CORS_ALLOWED_ORIGINS` | CORS origins (default `*`) | Production |

## 8. Documentation Map

| File | Purpose |
|------|---------|
| `docs/VISION.md` | Product vision, strategy, moat thesis (§1–§13) |
| `docs/DATA_MODEL_BRD.md` | Signal & data-model design spec (§1–§16) |
| `docs/PROJECT_STATUS.md` | This file — current state |
| `docs/TESTING_GUIDE.md` | Full testing playbook (8 sections) |
| `docs/specs/SPEC-01-migrations-and-first-signal.md` | Migration + signal slice (IMPLEMENTED) |
| `docs/specs/SPEC-02-offline-queue-and-sync.md` | Offline queue spec (NOT YET BUILT) |
| `docs/research/survey_short.md` | 3-min user research survey |
| `docs/research/survey_deep.md` | 8-min deep user research survey |
| `MASTER_BRD.md` | Technical BRD (points to VISION.md for strategy) |

## 9. Production Roadmap

| Phase | Status | Description |
|---|---|---|
| 1 | Done | Synthetic MVP (in-memory, all endpoints, all guardrails) |
| 2 | Ready | Supabase flip (3 imports + smoke test) |
| 3 | Done | Flutter mobile app (running E2E locally) |
| 4 | **Done** | Signal capture (SPEC-01 — migration + endpoint + emitter) |
| 5 | Spec written | Offline queue + sync (SPEC-02 — highest risk, pre-Laos) |
| 6 | Next | RevenueCat payments (keys + purchases_flutter) |
| 7 | Later | Play Store launch (real auth, real persistence, real payments) |
| 8 | Oct 2 | Laos field test (the moat-data capture trip) |

## 10. What's Next (priority order)

1. **SPEC-01 review complete** — reviewer confirmed contracts correct, gap fixed
2. **SPEC-02 implementation** — the hardest item; offline queue + sync (pre-Laos critical)
3. **Supabase flip** — 3 import changes to switch from in-memory to real persistence
4. **Seed venues** — `python seed_supabase.py` (16 Dubai venues into live DB)
5. **RevenueCat** — uncomment purchases_flutter, add keys
6. **Real auth** — Supabase Auth (magic link + Google Sign-In)
7. **Laos prep** — behavioral signal types, trip_party, consent UX
