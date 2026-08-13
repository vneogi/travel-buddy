# Travel Buddy -- Project Status

> Current state of the codebase. For commit history use `git log`.
> For the device-verification queue see docs/AWAITING_VERIFICATION.md.
> For engineering rules see docs/ENGINEERING_RULES.md.
> For which traveller and which cities, see docs/MARKET_STRATEGY.md.
> For measured per-city data coverage, see docs/CORRIDOR_COVERAGE.md.
> For the schema and data-layer sequence, see docs/DATA_LAYER_ROADMAP.md.

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
- Migrations 0011 to 0014 are committed and unapplied. 0011 waits on a live
  schema dump and diff. 0014 must not be applied at all in its current form --
  it declares node_id as UUID against an 8-character string. See Known Risks.
- Every file under data/ is ASCII-escaped, and a guard enforces it. Use
  scripts/format_venue_json.py to get a readable copy for curation and to
  re-escape on the way back in.
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
| Migration 0012 venue_external_id | COMMITTED, UNAPPLIED | Maps a venue to Wikidata, OSM, Google and Foursquare identifiers, unique on (source, external_id). Roadmap concern 2 |
| Migration 0013 taxonomy_term | COMMITTED, UNAPPLIED | Versions the controlled vocabulary across ten taxonomies, seeded from the venue and dish data. Roadmap concern 6 |
| Migration 0014 itinerary normalisation | COMMITTED, DO NOT APPLY | Creates trip_node and trip_edge. Blocked: node_id and edge_id are declared UUID, but TripNode.node_id has always been an 8-character hex string, which Postgres rejects. Applying it makes every Supabase trip save fail. In-memory does not type-check and the live tests skip without creds, which is why the suite is green |
| Venue loader | REPAIRED, CARRIES EVERY FIELD | Pure ASCII, vocabulary restored, geo_region inferred from the file wrapper. Payload built once in build_venue_record; insert and update derive from it so they cannot drift apart |
| Loader payload guard | DONE | A test asserts build_venue_record's key set equals VENUES_RAG_WRITE_COLUMNS. The earlier guards watched the declaration only, which is how four fields were dropped while the suite stayed green |
| External-id writer | DONE | upsert_venues writes venue_external_id for every venue carrying a verified name reference, and the test drives upsert_venues rather than the helper, which is the distinction that let the first attempt land as dead code |
| Localized names | PARTLY VERIFIED | Ten of 58 venues carry a name confirmed against Wikidata or OSM, with source and ref recorded. Three classes of wrong-script token are fixed. The remaining 48 stay source=generated |
| Curation round-trip | DONE | scripts/format_venue_json.py converts between the ASCII-escaped repo form and a readable UTF-8 copy under curation/, which is gitignored. Byte-identical round-trip is asserted |
| Signal capture (SPEC-01) | DONE | All registered types accepted, both backends |
| Offline queue (SPEC-02) | DONE | SQLite outbox, sync engine, crash recovery |
| Party context (SPEC-03) | DONE | Server-side stamping, both backends, migration 0003 applied |
| Observability (SPEC-05) | DONE | Ring buffer, request IDs, debug endpoint |
| Signal registry (SPEC-06) | DONE | models/signal_types.py plus drift test |
| Signal emission (SPEC-07) | PARTIAL | Missing in Dart: reroute_rejected, dish_loved, dish_ordered |
| Laos curation (SPEC-08) | DONE | 58 venues curated including Lao script. The wrong-script contamination is fixed: appended Chinese, Thai spelling of a Lao word, and a Thai-style consonant cluster |
| arrival_delta derivation | DONE | Server-derived from visited_confirmed vs scheduled_start |
| Docs hygiene guard | DONE | tests/test_docs_hygiene.py walks every markdown file outside build and vendor directories, and the SPEC-reference check also scans .py and .sql. Known non-ASCII files are allowlisted; the list may only shrink |
| Data format guard | DONE | Every data/ file is ASCII by byte count, venue and glossary files round-trip byte-identically, and Lao-script fields are checked for foreign script |
| Offline vault (SPEC-04) | SPECIFIED | Not implemented |
| Anonymous identity (SPEC-09) | SPECIFIED | Not implemented. Gates any tester build |
| Itinerary normalisation (SPEC-16) | IMPLEMENTED, MIGRATION BLOCKED | Decompose and compose land in services/itinerary_normaliser.py, dual-write in both backends, round-trip equality asserted, wire format unchanged. node_id is stable across reschedules via state_json. Two defects: the 0014 type mismatch above, and observed_duration_minutes is hardcoded None with no writer |
| Booking anchors (SPEC-10) | SPECIFIED | Not implemented. Resequenced to follow SPEC-16, because an anchor is a locked node and building it against the blob means building it twice. Amended so import is the primary path and manual entry the floor |
| Forced-choice preferences (SPEC-11) | SPECIFIED | Not implemented. Cold-start preference capture |
| Show driver cards (SPEC-12) | SPECIFIED | Schema and loader ready. No longer blocked: the card ships with an unconfirmed treatment plus a one-tap confirm that promotes a name to field_verified, so it works from day one and improves through use |
| Region and locale registry (SPEC-13) | SPECIFIED | Not implemented. Rising in priority: a city-onboarding pipeline needs it for bounding box, languages, currency and fare bands. Makes adding a city a row rather than a code change |
| Dietary model (SPEC-14) | DECIDED, DESCOPED | Not a feature. The spec is now a decision record: the app makes no dietary suitability claim, because no data source can support one. Ingredient facts stay as facts with a disclaimer. This is also how the halal-versus-pork hole closes |
| Trip checklist (SPEC-15) | SPECIFIED | Not implemented. Raw item text stays on the device; only a derived record syncs |
| Trust and verification (SPEC-17) | SPECIFIED | Not implemented, and it gates the three below. Owns attribute_claim plus the five display tiers: assert, hedge, ask, defer, refuse. No value crosses the API without its provenance, and the render layer refuses one that has none |
| On-demand venue discovery (SPEC-18) | SPECIFIED | Not implemented. A traveller asks about where they are standing and the answer persists as a provisional venue, so the venue layer grows from real demand. Coordinate anchoring against OSM or Wikidata is mandatory before anything persists |
| Corpus mining (SPEC-19) | SPECIFIED | Not implemented. Extracts the operational knowledge no structured dataset carries, from openly licensed corpora only. This is the data source trip_edge never had. Google and TripAdvisor are excluded on licensing |
| City onboarding kit (SPEC-20) | SPECIFIED | Not implemented. Seeds a city's spine of 40 to 60 anchors, sourced identity first so provenance defaults to sourced rather than generated. SPEC-18 supplies the tail. validate_city refuses rather than warns |

Migration numbers are assigned when a spec is implemented, not when it is
written. SPEC-11, SPEC-13, SPEC-14 and SPEC-15 each claimed a number, and the
numbers were taken by other work while they sat unimplemented.

## What is Next (Priority Order)

1. Fix migration 0014 before anything is applied: node_id and edge_id are
   declared UUID against an 8-character hex string. Then give
   observed_duration_minutes an actual writer, derived from arrival signals on
   sync rather than at save time, since it cannot be known when a trip is saved.
2. Dump the live schema and diff it against the migration set, then apply
   migrations 0011 to 0013 and re-load the three Laos files. Device task. The
   re-load also lands the opening hours that are currently null and the ten
   verified names.
3. Retire the dietary suitability claim, per the SPEC-14 decision record. This
   closes the halal-versus-pork hole by removing the claim rather than by adding
   a rule, which is the correct fix when no source can support the claim.
4. SPEC-17 trust and verification. It gates SPEC-18, SPEC-19 and SPEC-20, and it
   owns attribute_claim, which all three write into.
5. SPEC-12 driver card UI, including the confirm affordance that promotes a name
   to field_verified. The Oct 2 trip is the verification mechanism.
6. name_confirmed signal type, alongside driver_card_shown, in one migration.
7. SPEC-10 booking anchors, now unblocked by SPEC-16.
8. reroute_rejected plus swap sheet UI -- the last unwired behavioural signal.
9. SPEC-09 anonymous device identity -- prerequisite for any tester build.
10. Relocate VALID_DISH_CONTAINS to config/dietary.py (R5 violation).

Sequence the code changes before the re-load, not after.

The one task that cannot be done by an agent is judging whether a
transliterated venue name is what the signage actually says. A script test
catches Chinese where Lao belongs; it cannot catch a wrong vowel inside
otherwise correct Lao, and two such errors are known to exist. That is why the
driver card asks the traveller to confirm rather than asserting.

## Known Risks and Open Issues

Full detail is in docs/AWAITING_VERIFICATION.md.

| Issue | Severity | Detail |
|-------|----------|--------|
| Migration 0014 declares node_id as UUID | High | TripNode.node_id has always been str(uuid4())[:8], an 8-character string Postgres rejects as a UUID. Applying 0014 makes every Supabase trip save fail. The suite is green because in-memory does not type-check and the live tests skip without credentials. Do not apply 0014 until this is fixed |
| observed_duration_minutes has no writer | Medium | The column exists and a code comment claims it is populated from day one. Nothing populates it. It cannot be computed when a trip is saved, only derived from arrival signals on sync, so the transition data the convenience layer depends on is not accumulating |
| Live schema contains manual edits of unknown extent | High | Loads have been succeeding against columns no migration declared, so somebody added them by hand. PostgREST rejects writes to columns absent from its schema cache, so this is not a REST-layer quirk. Migration 0011 must not be applied before a dump and diff: if a hand-made name_local TEXT exists, ADD COLUMN IF NOT EXISTS names_local JSONB adds a second empty column and leaves the populated one unread |
| Dubai venue data has no source file | High | data/ holds only the Laos files. The 16 Dubai venues exist as rows in the hosted database and nowhere else, so a rebuild from migrations loses them. Export to version control before any rebuild |
| The dietary safety layer has no data source | RESOLVED BY DESCOPING | In OSM, diet:halal covers 20 of 6611 central Bangkok POIs and diet:vegetarian about two percent; Dubai is the best case at six and seven percent. A safety filter with no trustworthy input converts caution into misplaced confidence, so the claim is retired rather than sourced. See the SPEC-14 decision record |
| halal plus pork passes the allergen check | High until the claim is retired | No LABEL_EXCLUDES_ALLERGENS rule for halal, so a pork-serving venue passes a halal check. The fix is to stop making the claim, not to add the rule -- adding it would make the answer trustworthy-looking on data that cannot support it. Live until the retirement lands |
| Most localized names remain unverified | Medium | Forty-eight of 58 stay source=generated. Two known errors are a wrong vowel inside otherwise valid Lao, which no codepoint guard can detect. The driver card's confirm affordance is the mitigation |
| Lao order phrase may say fry, not spicy | Medium | The papaya salad phrase reads bo phat lai, not bo phet lai -- stir-fry rather than spicy, one missing vowel. Needs a native speaker, not a script check. Three of four hot dishes carry no moderating phrase at all, and the raw-meat laap has no cooked-request phrase |
| opening_hours null on all Laos venues | Medium | The loader writes opening_hours_structured correctly; the data has simply never been re-loaded since |
| hybrid_venue_search geo_region param | Medium | supabase_service passes a geo_region filter the RPC in 0001 does not declare. Verify against the live function |
| Raw-safety guard keys off English prose | Low | The guard that flags an uncooked dish looks for the word raw in the description, so rewording a description silently disables a safety check. Key it off a structured field |
| seniors overcorrected | Low | Set on 40 of 58 venues, roughly two thirds, so it cannot discriminate. mobility_limited is 17 of 58, which is plausible rather than overcorrected -- an earlier version of this table attributed the two-thirds figure to the wrong tag |
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

### Curate a venue file

Files under data/ are ASCII-escaped so tooling cannot silently drop characters.
To edit the local-script fields by hand:

    python scripts/format_venue_json.py --to-readable data/laos_vientiane.json
    # edit curation/laos_vientiane.json in an editor that shows Lao
    python scripts/format_venue_json.py --to-repo curation/laos_vientiane.json

### Flutter

    cd mobile
    flutter pub get
    flutter analyze
    flutter test

### PowerShell smoke test (Windows only)

    .\scripts\smoke-test.ps1
