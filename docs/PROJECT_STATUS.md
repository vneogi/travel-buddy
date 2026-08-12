# Travel Buddy -- Project Status

> Current state of the codebase. For commit history use `git log`.
> For the device-verification queue see docs/AWAITING_VERIFICATION.md.
> For engineering rules see docs/ENGINEERING_RULES.md.

## TL;DR

- Backend: FastAPI on Supabase (pgvector). db_provider resolves the backend at
  import time -- Supabase when creds are present, in-memory otherwise.
- Orchestrator: hand-rolled sequential pipeline in agents/state_machine.py
  (classify_intent -> check_cache -> venue_search -> apply_structural ->
  generate_response). NOT LangGraph -- langgraph is commented out in
  requirements.txt and the GraphState TypedDict is unused.
- AI: live via the LiteLLM gateway (gpt-4o heavy, gpt-4o-mini light,
  text-embedding-3-small embeddings).
- Data as last loaded: 74 venues (16 Dubai, 23 Luang Prabang, 15 Vang Vieng,
  20 Vientiane), 44 venue dishes, 30 dish-glossary entries. Confirm with a
  count query against venues_rag rather than trusting these numbers.
- Signals: the registry in models/signal_types.py is the source of truth for
  which types exist. A drift guard test enforces it.
- Flutter: offline-first with a SQLite outbox, sync engine, and typed exception
  hierarchy. Signal emission is wired for most but not all registered types --
  see the SPEC-07 row below.
- Test health: run `pytest -q -ra`. Counts are deliberately not recorded here
  (R16). The expected skips are the live-database tests in
  tests/test_supabase_integration.py, which skip when TB_SUPABASE_URL is unset.
  Any other skip is a finding, not a pass (R8).

## Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| Supabase persistence | LIVE | db_provider auto-resolves; falls back to in-memory |
| Migrations 0001-0010 | APPLIED, WITH DRIFT | 0007 RLS, 0008 hours JSONB, 0009 dish price, 0010 glossary. venues_rag lacks five columns the loader writes -- see Known Risks |
| Signal capture (SPEC-01) | DONE | All registered types accepted, both backends |
| Offline queue (SPEC-02) | DONE | SQLite outbox, sync engine, crash recovery |
| Party context (SPEC-03) | DONE | Server-side stamping, both backends, migration 0003 applied |
| Observability (SPEC-05) | DONE | Ring buffer, request IDs, debug endpoint |
| Signal registry (SPEC-06) | DONE | models/signal_types.py plus drift test |
| Signal emission (SPEC-07) | PARTIAL | Missing in Dart: reroute_rejected, dish_loved, dish_ordered |
| Laos curation (SPEC-08) | DONE, WITH GAPS | 58 venues loaded. See the spec for missed coverage targets |
| arrival_delta derivation | DONE | Server-derived from visited_confirmed vs scheduled_start |
| Docs hygiene guard | DONE | tests/test_docs_hygiene.py walks every markdown file outside build and vendor directories. 18 known non-ASCII files are allowlisted; the list may only shrink |
| Offline vault (SPEC-04) | SPECIFIED | Not implemented |
| Anonymous identity (SPEC-09) | SPECIFIED | Not implemented. Gates any tester build |
| Booking anchors (SPEC-10) | SPECIFIED | Not implemented. Chosen scope for the Oct 2 field test |
| Forced-choice preferences (SPEC-11) | SPECIFIED | Not implemented. Cold-start preference capture |
| Show driver cards (SPEC-12) | SPECIFIED | Blocked: venues_rag has no name_local or nearest_landmark |

## What is Next (Priority Order)

1. SPEC-10 booking anchors -- chosen scope for the Oct 2 Laos field test, so
   the engine knows the real trip. Backend first, all pytest-verifiable.
2. halal plus pork LABEL_EXCLUDES_ALLERGENS rule -- High-severity safety hole
3. venues_rag missing-column migration -- latent break, and unblocks SPEC-12
4. Venue loader repair -- it cannot load the Laos files as committed
5. reroute_rejected plus swap sheet UI -- the last unwired behavioural signal
6. SPEC-09 anonymous device identity -- prerequisite for any tester build
7. Backfill opening_hours on the 58 Laos venues (loader fix landed, needs re-run)
8. Relocate VALID_DISH_CONTAINS to config/dietary.py (R5 violation)

Lao-script curation for SPEC-12 runs in parallel with all of the above. It has
no tooling dependency, cannot be done by an agent, and has the longest lead
time of anything remaining.

## Known Risks and Open Issues

Full detail, including three loader defects, is in docs/AWAITING_VERIFICATION.md.

| Issue | Severity | Detail |
|-------|----------|--------|
| Venue loader cannot load the Laos data | High | The vocabulary expansion was reverted by a merge, and an unassigned variable raises NameError without --geo-region |
| venues_rag schema drift | High | The loader writes typical_dwell_minutes, indoor_outdoor and price_band; no migration defines them. name_local and nearest_landmark are also absent, which blocks SPEC-12. A database rebuilt from migrations today fails on load |
| halal plus pork passes the allergen check | High | No LABEL_EXCLUDES_ALLERGENS rule for halal. Safety hole for Muslim travellers |
| opening_hours null on all Laos venues | Medium | Loader field-name fix committed but the data was never re-loaded |
| hybrid_venue_search geo_region param | Medium | supabase_service passes a geo_region filter the RPC in 0001 does not declare. Verify against the live function |
| pytest floor over-pinned | Low | requirements-dev pins pytest>=9.0.0. The config only needs PytestReturnNotNoneWarning, which is missing solely in 8.4.0, so the accurate floor is 8.4.1 |
| mobility_limited overcorrected | Low | Set on roughly two thirds of venues -- too loose to be a useful filter |
| Vientiane has zero massage_spa | Low | A natural fatigue-reroute target is missing in one region |
| VALID_DISH_CONTAINS in the wrong file | Low | Lives in load_dish_glossary.py, belongs in config/dietary.py (R5) |

## How to Run

### Backend (local)

    git pull origin main
    pip install -r requirements.txt
    cp .env.example .env   # fill in Supabase and OpenAI creds
    uvicorn main:app --reload

### Tests

    pip install -r requirements-dev.txt
    pytest -q -ra

Install the dev requirements first. The pytest config names a warning class in
`filterwarnings`, and pytest 8.4.0 shipped without that class, so on that one
release pytest errors before collecting anything.

### Load venues (Laos)

Read docs/AWAITING_VERIFICATION.md first. The loader has open defects and
`--geo-region` is mandatory in practice, because without it an unassigned
variable raises NameError.

    # Requires OPENAI_API_KEY, TB_SUPABASE_URL, TB_SUPABASE_KEY
    python scripts/load_dish_glossary.py data/laos_dish_glossary.json --dry-run
    python scripts/load_venues.py data/laos_luang_prabang.json --geo-region <region> --dry-run

Drop `--dry-run` only once the dry run reports zero errors.

### Flutter

    cd mobile
    flutter pub get
    flutter analyze
    flutter test

### PowerShell smoke test (Windows only)

    .\scripts\smoke-test.ps1
