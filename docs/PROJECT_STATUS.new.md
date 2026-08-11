# Travel Buddy -- Project Status

> Current state of the codebase. For commit history use `git log`.
> For device-verification queue see docs/AWAITING_VERIFICATION.md.
> For engineering rules see docs/ENGINEERING_RULES.md.

## TL;DR

- Backend: FastAPI on Supabase (pgvector). db_provider resolves backend at
  import time -- Supabase when creds present, in-memory otherwise.
- Orchestrator: hand-rolled sequential pipeline in agents/state_machine.py
  (classify_intent -> check_cache -> venue_search -> apply_structural ->
  generate_response). NOT LangGraph -- langgraph is commented out in
  requirements.txt and GraphState TypedDict is unused.
- AI: live via LiteLLM gateway (gpt-4o heavy, gpt-4o-mini light,
  text-embedding-3-small embeddings).
- Data: 74 venues total (16 Dubai, 23 Luang Prabang, 15 Vang Vieng,
  20 Vientiane). 44 venue dishes. 30 dish-glossary entries.
- Signals: 8 types registered in models/signal_types.py.
- Flutter: offline-first with SQLite outbox, sync engine, typed exception
  hierarchy. Behavioral signal emission wired for 5 of 8 types.
- Test health: run `pytest -q` (do not hardcode counts here -- R16).

## Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| Supabase persistence | LIVE | db_provider auto-resolves; fallback to in-memory |
| Migrations 0001-0010 | APPLIED | 0007 RLS, 0008 hours JSONB, 0009 dish price, 0010 glossary |
| Signal capture (SPEC-01) | DONE | All 8 types accepted, both backends |
| Offline queue (SPEC-02) | DONE | SQLite outbox, sync engine, crash recovery |
| Party context (SPEC-03) | DONE | Server-side stamping, both backends, migration 0003 applied |
| Observability (SPEC-05) | DONE | Ring buffer, request IDs, debug endpoint |
| Signal registry (SPEC-06) | DONE | models/signal_types.py + drift test |
| Signal emission (SPEC-07) | PARTIAL | 5/8 wired in Dart. Missing: reroute_rejected, dish_loved, dish_ordered |
| Laos curation (SPEC-08) | DONE | 58 venues loaded, validation rules enforced (see spec) |
| Offline vault (SPEC-04) | SPECIFIED | Not implemented |
| Anonymous identity (SPEC-09) | SPECIFIED | Not implemented |
| Booking anchors (SPEC-10) | SPECIFIED | Not implemented |

## What is Next (Priority Order)

1. arrival_delta server derivation -- pure backend, pytest-verifiable
2. reroute_rejected + swap sheet UI -- last missing behavioural signal
3. SPEC-09 anonymous device identity -- prerequisite for tester builds
4. Backfill opening_hours on 58 Laos venues (field-name fix landed, needs re-run)
5. Fix VALID_DISH_CONTAINS location (R5 violation)
6. halal + pork LABEL_EXCLUDES rule

## Known Risks and Open Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| opening_hours null on all Laos venues | Medium | Loader field-name fix committed but data not re-loaded |
| halal + pork passes allergen check | High | No LABEL_EXCLUDES_ALLERGENS rule for halal. Safety hole for Muslim travellers |
| mobility_limited overcorrected | Low | Set on 65% of venues -- too loose to be a useful filter |
| Vientiane zero massage_spa | Low | Natural fatigue-reroute target missing in one region |
| VALID_DISH_CONTAINS in wrong file | Low | Lives in load_dish_glossary.py, belongs in config/dietary.py (R5) |
| Entity resolution broken | Fixed | venue_name -> name column mismatch fixed in code review commit |

## How to Run

### Backend (local)

    git pull origin main
    pip install -r requirements.txt
    cp .env.example .env   # fill in Supabase + OpenAI creds
    uvicorn main:app --reload

### Tests

    pytest -q --tb=short

Skip reason: supabase client library not installed (1 test).

### Load venues (Laos)

    # Set OPENAI_API_KEY and TB_SUPABASE_URL/TB_SUPABASE_SERVICE_KEY
    python scripts/load_dish_glossary.py data/laos_dish_glossary.json
    python scripts/load_venues.py data/laos_luang_prabang.json data/laos_vang_vieng.json data/laos_vientiane.json

### Flutter

    cd mobile
    flutter pub get
    flutter analyze
    flutter test

### PowerShell smoke test (Windows only)

    .\scripts\smoke-test.ps1
