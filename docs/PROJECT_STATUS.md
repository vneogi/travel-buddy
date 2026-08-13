# Travel Buddy -- Project Status

> Current state of the codebase. For commit history use `git log`.
> For the device-verification queue see docs/AWAITING_VERIFICATION.md.
> For engineering rules see docs/ENGINEERING_RULES.md.
> For which traveller and which cities, see docs/MARKET_STRATEGY.md.

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
- Migration 0011 is committed and unapplied, and must stay that way until the
  live schema is dumped and diffed. See Known Risks.
- Test health: run `pytest -q -ra`. Counts are deliberately not recorded here
  (R16). The expected skips are the live-database tests in
  tests/test_supabase_integration.py, which skip when TB_SUPABASE_URL is unset.
  Any other skip is a finding, not a pass (R8).

## Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| Supabase persistence | LIVE | db_provider auto-resolves; falls back to in-memory |
| Migrations 0001-0010 | APPLIED | 0005 entity_ref generalization, 0007 RLS, 0008 hours JSONB, 0009 dish price, 0010 glossary |
| Migration 0011 | COMMITTED, UNAPPLIED | Complete. Eight additive columns: typical_dwell_minutes, indoor_outdoor, price_band, has_aircon, nearest_landmark, wheelchair_notes, and names_local plus landmarks_local as JSONB. Gated on the live schema dump, not on further authoring |
| Venue loader | REPAIRED, CARRIES EVERY FIELD | Pure ASCII, vocabulary restored, geo_region inferred from the file wrapper. Payload built once in build_venue_record; insert and update derive from it so they cannot drift apart |
| Loader payload guard | DONE | A test asserts build_venue_record's key set equals VENUES_RAG_WRITE_COLUMNS. The earlier guards watched the declaration only, which is how four fields were dropped while the suite stayed green |
| Localized names | LOADED AS UNVERIFIED | Every Lao name and landmark carries source=generated. SPEC-12 says the driver card will not present a generated name as authoritative, so the card degrades to English for all 58 venues until they are verified |
| Signal capture (SPEC-01) | DONE | All registered types accepted, both backends |
| Offline queue (SPEC-02) | DONE | SQLite outbox, sync engine, crash recovery |
| Party context (SPEC-03) | DONE | Server-side stamping, both backends, migration 0003 applied |
| Observability (SPEC-05) | DONE | Ring buffer, request IDs, debug endpoint |
| Signal registry (SPEC-06) | DONE | models/signal_types.py plus drift test |
| Signal emission (SPEC-07) | PARTIAL | Missing in Dart: reroute_rejected, dish_loved, dish_ordered |
| Laos curation (SPEC-08) | DONE, WITH DEFECTS | 58 venues curated including Lao script. Twelve fields carry the wrong script -- see Known Risks |
| arrival_delta derivation | DONE | Server-derived from visited_confirmed vs scheduled_start |
| Docs hygiene guard | DONE | tests/test_docs_hygiene.py walks every markdown file outside build and vendor directories, and the SPEC-reference check also scans .py and .sql. Known non-ASCII files are allowlisted; the list may only shrink |
| Offline vault (SPEC-04) | SPECIFIED | Not implemented |
| Anonymous identity (SPEC-09) | SPECIFIED | Not implemented. Gates any tester build |
| Booking anchors (SPEC-10) | SPECIFIED | Not implemented. Chosen scope for the Oct 2 field test. Also unlocks most of the convenience layer, which needs an anchor to mean anything by your hotel or by your drop-off |
| Forced-choice preferences (SPEC-11) | SPECIFIED | Not implemented. Cold-start preference capture |
| Show driver cards (SPEC-12) | SPECIFIED | Schema and loader are ready. Blocked on name verification, not on curation or on code |
| Region and locale registry (SPEC-13) | SPECIFIED | Not implemented. Post-Laos. Migration 0015. Makes adding a city a row rather than a code change |
| Dietary model (SPEC-14) | SPECIFIED | Not implemented. Post-Laos. Migration 0016. The halal-versus-pork fix inside it is standalone and should not wait |
| Trip checklist (SPEC-15) | SPECIFIED | Not implemented. Post-Laos. Migration 0017. Raw item text stays on the device; only a derived record syncs |

## What is Next (Priority Order)

1. Verify the Lao names against Wikidata and OSM, and fix the twelve
   wrong-script fields. This is now the critical path for driver cards: the
   feature is built and switched off until names carry a verified source.
2. Dump the live schema and diff it against the migration set, then apply
   migration 0011 and re-load the three Laos files. Device task. The re-load
   also lands the opening hours that are currently null.
3. SPEC-10 booking anchors -- chosen scope for the Oct 2 Laos field test, so
   the engine knows the real trip. Backend first, all pytest-verifiable.
4. SPEC-12 driver card UI, once names are verified and 0011 is applied.
5. halal plus pork LABEL_EXCLUDES_ALLERGENS rule -- high-severity safety hole.
   Standalone; do not wait for SPEC-14.
6. reroute_rejected plus swap sheet UI -- the last unwired behavioural signal
7. SPEC-09 anonymous device identity -- prerequisite for any tester build
8. Relocate VALID_DISH_CONTAINS to config/dietary.py (R5 violation)

Sequence the code changes before the re-load, not after.

The one task that cannot be done by an agent is judging whether a
transliterated venue name is what the signage actually says. A script test
catches Chinese where Lao belongs; it cannot tell a real transliterated name
from an invented one. Wikidata and OSM can settle the landmarks and temples;
small restaurants will stay unverified, and that is the correct outcome rather
than a gap.

## Known Risks and Open Issues

Full detail is in docs/AWAITING_VERIFICATION.md.

| Issue | Severity | Detail |
|-------|----------|--------|
| Live schema contains manual edits of unknown extent | High | Loads have been succeeding against columns no migration declared, so somebody added them by hand. PostgREST rejects writes to columns absent from its schema cache, so this is not a REST-layer quirk. Migration 0011 must not be applied before a dump and diff: if a hand-made name_local TEXT exists, ADD COLUMN IF NOT EXISTS names_local JSONB adds a second empty column and leaves the populated one unread |
| Dubai venue data has no source file | High | data/ holds only the Laos files. The 16 Dubai venues exist as rows in the hosted database and nowhere else, so a rebuild from migrations loses them. Export to version control before any rebuild |
| Every localized name is unverified | High | All Lao names and landmarks load with source=generated, which is accurate -- they came from a model. SPEC-12 refuses to present a generated name as authoritative, so the driver card shows English for all 58 venues until verification runs |
| halal plus pork passes the allergen check | High | No LABEL_EXCLUDES_ALLERGENS rule for halal. Safety hole for Muslim travellers. SPEC-14 subsumes it, but the fix is standalone |
| Wrong script in Lao-language fields | Medium | Seven name_local values contain Mandarin, five nearest_landmark_local values contain Thai. Machine-detectable by codepoint range. Counts to be re-confirmed against the data as part of the verification pass |
| opening_hours null on all Laos venues | Medium | The loader writes opening_hours_structured correctly; the data has simply never been re-loaded since |
| hybrid_venue_search geo_region param | Medium | supabase_service passes a geo_region filter the RPC in 0001 does not declare. Verify against the live function |
| Taxonomy is unguarded | Medium | vibe_tags, audience, price_band, dwell and cuisine are the only things that carry a traveller's taste between cities with no shared venues. The vocabulary was silently reverted once by merge c5f64f3 and nothing versions it. The cost of a rename grows with every city tagged |
| mobility_limited overcorrected | Low | Set on roughly two thirds of venues. wheelchair_notes is now written by the loader but has not yet reached the database, because 0011 is unapplied |
| Vientiane has zero massage_spa | Low | Suspect. This was reported by a warning function that was broken until recently, so re-check it against the data rather than trusting the earlier report |
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

The loader infers the region from the file wrapper, so `--geo-region` is
optional. A dry run needs no credentials.

    python scripts/load_venues.py data/laos_luang_prabang.json data/laos_vang_vieng.json data/laos_vientiane.json --dry-run

For a real load, set OPENAI_API_KEY, TB_SUPABASE_URL and TB_SUPABASE_KEY, then
drop `--dry-run` once the dry run reports zero errors.

    python scripts/load_dish_glossary.py data/laos_dish_glossary.json --dry-run

### Flutter

    cd mobile
    flutter pub get
    flutter analyze
    flutter test

### PowerShell smoke test (Windows only)

    .\scripts\smoke-test.ps1
