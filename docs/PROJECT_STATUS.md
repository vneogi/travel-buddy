# Travel Buddy — Project Status & Handoff

> Single source of truth for where the project stands and what remains.
> Last updated: 2026-08-06 (v8.0). Keep this file updated as milestones complete.

## 0. TL;DR (verified 2026-08-08)

- **Backend**: functionally complete, hardened, **53 unit tests passing** + 5 skipped
  (Supabase integration). Signal capture + offline-sync server support live.
- **AI**: live via OpenAI (gpt-4o heavy, gpt-4o-mini light, text-embedding-3-small).
- **Supabase**: schema + functions deployed, signal tables ready (migration 0002).
  Venues NOT seeded. Backend still uses in-memory datastore (flip = 3 imports).
  **Migration 0003 (trip_party) NOT YET WRITTEN — blocks Supabase flip for SPEC-03.**
- **Flutter**: running end-to-end on Android (real device). **29+ unit tests**.
  Offline-first queue fully implemented. Offline create-trip crash fixed.
- **Signal capture (SPEC-01)**: fully implemented + reviewed. All backends.
- **Offline queue (SPEC-02)**: **IMPLEMENTED** — SQLite outbox, sync engine, typed
  exception handling, crash recovery, debug view, app-resume lifecycle.
- **Party context (SPEC-03)**: **PARTIAL** — Python backend complete (server-side stamping
  at ingest, both backends have save/get_trip_party, 8 tests pass). BUT: Supabase
  migration 0003 never written. `supabase_service.save_trip_party` will raise at runtime.
  Do not flip `db_provider` to Supabase before migration lands.
- **Behavioral signals**: **NOT STARTED**. Only `user_loved` registered in
  `_valid_signal_types`. The 6 other types specified in DATA_MODEL §4.2 would be
  rejected 422 today. This is the #1 moat gap.
- **Observability (SPEC-05)**: IMPLEMENTED — ring buffer, request IDs, debug endpoint.
- **Migrations**: versioned tooling in place (`supabase/migrations/`).

### Known risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| **Registry drift** | `_valid_signal_types` hardcoded in database_service.py with comment "mirrors signal_type table" — two sources of truth for one registry | SPEC-06 replaces with single `models/signal_types.py` + drift test |
| **SPEC-03 incomplete** | Supabase flip blocked until 0003 migration lands | Write migration before flipping |
| **Thin signal data** | Laos trip captures only ❤ taps without behavioral types | SPEC-06 registers types; SPEC-07 wires client emission |

## 1. Commit History (all pushed to main)

| # | Message | Key files |
|---|---------|-----------|
| 1–29 | (Flutter phase — see v6.0 summary) | Full backend + mobile scaffold |
| 30 | `docs: Add VISION.md` | docs/VISION.md |
| 31 | `docs: Add user research surveys` | docs/research/ |
| 32 | `docs: Extend VISION.md — capabilities matrix` | docs/VISION.md |
| 33 | `docs: Extend DATA_MODEL_BRD.md §16` | docs/DATA_MODEL_BRD.md |
| 34 | `docs: Add SPEC-01` | docs/specs/ |
| 35 | `feat(migrations): SPEC-01 Part A` | supabase/migrations/ |
| 36 | `feat(signals): SPEC-01 Part B` | 12 files |
| 37 | `docs: Add SPEC-02` | docs/specs/ |
| 38 | `fix(signals): Add record_signal to SupabaseService` | supabase_service.py |
| 39 | `fix: Replace datetime.utcnow() with timezone-aware` | 9 files |
| 40 | `docs: Update PROJECT_STATUS.md to v7.0` | docs/ |
| 41 | `feat(offline): SPEC-02 — offline-first queue + sync` | 9 files |
| 42 | `fix(offline): Address SPEC-02 review — lifecycle + exceptions` | 5 files |

### Commit #41 — SPEC-02 Implementation
- `mobile/lib/offline/offline_database.dart`: SQLite outbox + cache tables
- `mobile/lib/offline/sync_engine.dart`: sync algorithm with backoff
- `mobile/lib/services/signal_service.dart`: rewritten — queue-backed emit()
- `mobile/lib/core/providers.dart`: wires OfflineDatabase + SyncEngine
- `mobile/lib/features/debug/sync_status_screen.dart`: debug view
- `mobile/test/offline_sync_test.dart`: 10 offline tests
- `routers/signal_router.py`: Part C (per-item rejection, skew tolerance)
- `tests/test_signals.py`: 12 tests (6 new Part C)
- `mobile/pubspec.yaml`: sqflite, path, connectivity_plus

### Commit #42 — Review Fixes (two blocking bugs)
- `mobile/lib/main.dart`: ProviderContainer + SyncEngine.start() + app-resume
- `mobile/lib/offline/sync_engine.dart`: typed exception catching (not string-matching)
- `mobile/test/offline_sync_test.dart`: tests throw real exception types + test 11
- `mobile/lib/routing/app_router.dart`: /profile/sync route
- `mobile/lib/features/profile/profile_screen.dart`: sync status nav link

## 2. Test Results

**Backend (pytest):** `53 passed, 5 skipped`
- 12 signal tests (6 SPEC-01 + 6 SPEC-02 Part C)
- 8 party/SPEC-03 tests
- 7 observability/SPEC-05 tests
- 5 skipped = Supabase integration tests (need live DB)

**Flutter (expected):** `29 tests`
- 14 core (models, repositories, itinerary controller)
- 4 signal service (wire format, error swallow)
- 11 offline (durability, sync, crash recovery, backoff, typed errors)

## 3. Architecture

```
Flutter App (mobile/)
  └─ SignalService (queue-backed — SPEC-02)
       └─ OfflineDatabase (SQLite outbox + cache)
       └─ SyncEngine (single-flight, typed exceptions, backoff)
            └─ POST /api/v1/signals (batch, idempotent)
  └─ ApiClient (Dio + typed exceptions)
  └─ StateNotifier controllers (Riverpod)
  └─ WidgetsBindingObserver (app-resume → triggerSync)

FastAPI Backend
  ├─ routers/signal_router.py     (SPEC-02 Part C: per-item, skew, rejected[])
  ├─ routers/trip_router.py       (trip CRUD + events)
  ├─ routers/payment_router.py    (RevenueCat webhooks)
  ├─ security.py                  (JWT + debug auth)
  ├─ agents/state_machine.py      (LangGraph orchestrator)
  ├─ services/database_service.py (in-memory — active)
  ├─ services/supabase_service.py (production — ready, not flipped)
  └─ services/cache_service.py    (semantic cache)

Supabase (PostgreSQL + pgvector)
  ├─ 0001_initial_schema.sql      (5 tables, 5 functions)
  └─ 0002_signals_core.sql        (source, signal_type, signal)
```

## 4. SPEC-02 Implementation (Offline Queue + Sync)

**Status: IMPLEMENTED + REVIEWED (commits #41–42)**

Key components:
- **OfflineDatabase** (`sqflite`): outbox table (signal_id PK, state machine), cache tables
- **SignalService**: emit() persists to outbox BEFORE network; never throws/blocks
- **SyncEngine**: single-flight, batch POST, exponential backoff + jitter (cap 15min)
  - Typed exception handling: `UnauthorizedException` → preserve; `ServerException`/`NetworkException` → retry; other → permanent
  - Crash recovery on startup (inflight → pending)
  - Triggers: app start, resume, connectivity regained, post-emit, 60s timer
- **Sync Status Screen**: `/profile/sync` — pending/inflight/failed counts, force-sync
- **Server Part C**: per-item rejection, 30d captured_at skew tolerance, `rejected[]` response

**Review findings fixed:**
1. ~~SyncEngine.start() never called~~ → wired in main.dart with ProviderContainer
2. ~~String-matching exception text~~ → typed catch clauses matching ApiClient's hierarchy
3. ~~Dead markInflight([])~~ → removed
4. ~~Sync status unreachable~~ → route + profile link added

## 5. Documentation Map

| File | Purpose |
|------|---------|
| `docs/VISION.md` | Product vision, strategy, moat thesis (§1–§13) |
| `docs/DATA_MODEL_BRD.md` | Signal & data-model design spec (§1–§16) |
| `docs/PROJECT_STATUS.md` | This file — current state |
| `docs/TESTING_GUIDE.md` | Full testing playbook |
| `docs/specs/SPEC-01-migrations-and-first-signal.md` | IMPLEMENTED |
| `docs/specs/SPEC-02-offline-queue-and-sync.md` | IMPLEMENTED |
| `docs/research/survey_short.md` | 3-min user research survey |
| `docs/research/survey_deep.md` | 8-min deep user research survey |
| `MASTER_BRD.md` | Technical BRD (points to VISION.md for strategy) |

## 6. Production Roadmap

| Phase | Status | Description |
|---|---|---|
| 1 | Done | Synthetic MVP (in-memory, all endpoints, all guardrails) |
| 2 | **Blocked** | Supabase flip (3 imports — blocked by missing 0003 migration) |
| 3 | Done | Flutter mobile app (running E2E on real device) |
| 4 | **Done** | Signal capture (SPEC-01 — migration + endpoint + emitter) |
| 5 | **Done** | Offline queue + sync (SPEC-02 — implemented + review-fixed) |
| 5b | **Done** | Observability (SPEC-05 — ring buffer, request IDs, debug endpoint) |
| 5c | **Partial** | Party context (SPEC-03 — backend code complete, migration missing) |
| 6 | **Next** | Behavioral signal types (SPEC-06 — #1 moat priority) |
| 7 | Later | RevenueCat payments (keys + purchases_flutter) |
| 8 | Later | Play Store launch (real auth, real persistence, real payments) |
| 9 | Oct 2 | Laos field test (airplane-mode drill must pass first) |


### UX & Vault (new, P1)
- `docs/UX_BACKLOG.md` — adopted UX ideas, prioritized; **§0 lists frozen architecture decisions**
- `docs/specs/SPEC-04-offline-vault.md` — Offline Vault / Rescue Pack (P1, capability #7)
- VISION §14 (Travelogue reciprocity), §15 (tourism-board distribution), §16 (UX direction)
- DATA_MODEL §17 (vault cache tables + pre-caching rule)

**Priority remains moat-first:** airplane-mode drill → Supabase flip → SPEC-03 `party_context` →
behavioral signal types → **then** SPEC-04 Vault + map-first shell if time before Oct 2.

### Observability & UI feedback (commits #48–54)
- **SPEC-05 implemented** (`monitoring/error_log.py`, `routers/debug_router.py`, `main.py`):
  - Global exception handler logs full tracebacks — no silent 500s
  - Request middleware adds `X-Request-ID` + timing to every response
  - Ring buffer (capped at 100) readable via `GET /api/v1/debug/errors`
  - Debug endpoint 404s when `settings.debug` is off (production-safe)
  - Startup config log uses booleans only — never secret values
  - All `print()` replaced with structured `logging`
- **UI fixes**: filled heart (isLoved), visible swap button, keyed rebuild for AnimatedSwitcher
- **Dev scripts**: `scripts/dev.ps1` (check/backend/app/tunnel/verify modes)
- **Regression tests**: `tests/test_user.py` — locks in the UserTier fix
- **Test count: 45 passed, 5 skipped** (was 33+5 at start of session)

## 7. What's Next (priority order, verified 2026-08-08)

1. **SPEC-06: Behavioral signal types** — register 5 types server-side. #1 moat gap.
2. **Migration 0003** — trip_party + party_member tables (completes SPEC-03, unblocks Supabase flip)
3. **Airplane-mode drill** (must pass before Laos):
   - Use `app-lan` mode (not USB tunnel). Airplane mode → tap loved on 5 venues →
     force-kill app → reopen → still 5 pending → enable network → all sync → 5 rows in Supabase
4. **Supabase flip** — 3 import changes to switch to real persistence (after 0003 lands)
5. **Seed venues** — real Laos venues for the field test
6. **SPEC-07: Client signal emission** — swap-accept → reroute_accepted, manual confirm → visited_confirmed
7. **Real auth** — Supabase Auth (magic link + Google Sign-In)
8. **Laos prep** — consent UX, offline vault if time

## 8. Running Locally

**Backend:**
```bash
cd travel-buddy
pip install -r requirements.txt
export TB_DEBUG=true
uvicorn main:app --reload --port 8000
# Tests: pytest -q (expect 33 passed, 5 skipped)
```

**Flutter:**
```bash
cd mobile
flutter pub get
flutter run -d chrome \
  --dart-define=TB_API_BASE_URL=http://localhost:8000 \
  --dart-define=TB_DEBUG_USER_ID=11111111-1111-1111-1111-111111111111
# Tests: flutter test (expect 29 passed)
```
