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
- Migrations 0011 to 0018 are committed and unapplied, and all eight are now
  applicable. 0011 is the only one still gated, on a live schema dump and diff,
  because the live schema carries hand-made columns. 0014's UUID defect and
  0015's two preconditions were fixed in 7c20b5f and f012253. 0015 remains the
  only one that is not purely additive, since it drops and re-adds a CHECK, but
  the new CHECK is added NOT VALID and so cannot abort on existing rows. 0016 is
  comments only.
- Every file under data/ is ASCII-escaped, and a guard enforces it. Use
  scripts/format_venue_json.py to get a readable copy for curation and to
  re-escape on the way back in.
- Test health: run `pytest -q -ra`. Counts are deliberately not recorded here
  (R16). The expected skips are the live-database tests in
  tests/test_supabase_integration.py, which skip when TB_SUPABASE_URL is unset.
  Any other skip is a finding, not a pass (R8). Those five have never once run
  with credentials, which is itself a finding -- see Known Risks.

## Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| Supabase persistence | LIVE | db_provider auto-resolves; falls back to in-memory |
| Migrations 0001-0010 | APPLIED | 0005 entity_ref generalization, 0007 RLS, 0008 hours JSONB, 0009 dish price, 0010 glossary |
| Migration 0011 | COMMITTED, UNAPPLIED | Complete. Eight additive columns: typical_dwell_minutes, indoor_outdoor, price_band, has_aircon, nearest_landmark, wheelchair_notes, and names_local plus landmarks_local as JSONB. Gated on the live schema dump, not on further authoring |
| Migration 0012 venue_external_id | COMMITTED, UNAPPLIED | Maps a venue to Wikidata, OSM, Google and Foursquare identifiers, unique on (source, external_id). Roadmap concern 2 |
| Migration 0013 taxonomy_term | COMMITTED, UNAPPLIED | Versions the controlled vocabulary across ten taxonomies, seeded from the venue and dish data. Roadmap concern 6 |
| Migration 0014 itinerary normalisation | COMMITTED, UNAPPLIED | Creates trip_node and trip_edge. node_id and edge_id are TEXT, which matches the 8-character hex IDs the application generates. The earlier UUID declaration would have failed every Supabase trip save; fixed in 7c20b5f, along with extracting both ID generators into models/ids.py |
| Migration 0015 drift fixes | COMMITTED, UNAPPLIED | Four fixes: venue_dish.price_band CHECK realigned to the taxonomy_term seed, venue_dish.names_local JSONB with a backfill, venue_dish.currency_code plus an explicit minor-unit rule, and embedding_model on venues_rag and cached_responses. Not purely additive, since it drops and re-adds a CHECK, but the new CHECK is NOT VALID and the backfill is scoped to the Laos regions by joining venues_rag. Both preconditions were cleared in f012253; two follow-ups remain rather than blockers |
| Migration 0016 comment fixes | COMMITTED, UNAPPLIED | Comments only, no schema change, idempotent. Re-issues the dish_glossary table comment in ASCII, because 0010 was applied while it held an em-dash and editing the 0010 file corrected future builds without touching the live pg_description. Also rewrites the suitable_for column comment to record the SPEC-14 retirement, so the database stops documenting a claim we no longer make |
| Migration 0017 venues_rag price_band | COMMITTED, UNAPPLIED | Adds the CHECK that 0011 omitted, NOT VALID so it cannot abort on live rows, with the VALIDATE line commented out for after the distinct values are read. Paired with a test that compares the CHECK terms against the taxonomy_term seed as sets rather than by substring |
| Migration 0018 anonymous identity | COMMITTED, UNAPPLIED | Adds identity_kind to user_tiers, defaulting to unknown rather than anonymous so it asserts nothing about rows nobody verified, with a CHECK over anonymous, supabase and unknown. Written by upgrade-on-sight in both backends: a known kind promotes a lesser one and nothing ever demotes, so call ordering cannot strand a row as unknown. In the Supabase backend the promotion UPDATE carries an in_ filter naming the strictly-lower kinds, so correctness lives in the statement rather than in a read-then-write that two threads can interleave |
| Venue loader | REPAIRED, CARRIES EVERY FIELD | Pure ASCII, vocabulary restored, geo_region inferred from the file wrapper. Payload built once in build_venue_record; insert and update derive from it so they cannot drift apart |
| Loader payload guard | DONE | A test asserts build_venue_record's key set equals VENUES_RAG_WRITE_COLUMNS, and build_dish_record does the same for venue_dish against VENUE_DISH_WRITE_COLUMNS. The earlier guards watched the declaration only, which is how four fields were dropped while the suite stayed green |
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
| Docs hygiene guard | DONE | tests/test_docs_hygiene.py walks every markdown file outside build and vendor directories, and the SPEC-reference check also scans .py and .sql. Known non-ASCII files are allowlisted; the list may only shrink. The ASCII check itself still covers markdown only |
| Data format guard | DONE | Every data/ file is ASCII by byte count, venue and glossary files round-trip byte-identically, and Lao-script fields are checked for foreign script |
| Offline vault (SPEC-04) | SPECIFIED, OCTOBER SHRUNK | Full vault not on the October path. SPEC-02 already delivers outbox, SyncEngine, cache_trip and cache_place; SPEC-12 already owns the venue driver card on that cache. October keeps only a thin rescue entry to the hotel address card once SPEC-10 exists. cache_vault, passes, emergency grid and phrase packs stay post-field-test -- see SPEC-04 |
| Anonymous identity (SPEC-09) | SERVER HALF IMPLEMENTED | The client half is still owed. Server side is done and verified: resolution order is JWT, then Anonymous, then the debug header, failing closed; TB_ALLOW_ANONYMOUS defaults to False; the raw Authorization header is parsed rather than loosening HTTPBearer, which would have rejected a non-Bearer scheme; UUIDs must be version 4 with the RFC 4122 variant, so v1 is refused and its embedded MAC address never reaches us; and non-canonical spellings are rejected rather than normalised, so one UUID cannot become five distinct user ids. Migration 0018 carries identity_kind |
| Itinerary normalisation (SPEC-16) | IMPLEMENTED | Decompose and compose land in services/itinerary_normaliser.py, dual-write in both backends, round-trip equality asserted, wire format unchanged. node_id is stable across reschedules via state_json and now comes from models/ids.py. One gap remains: observed_duration_minutes has no writer, so no transition data is accumulating |
| Booking anchors (SPEC-10) | SPECIFIED | Not implemented. Resequenced to follow SPEC-16, because an anchor is a locked node and building it against the blob means building it twice. Amended so import is the primary path, manual entry the floor, and extraction on the device the preferred implementation of every import path |
| Forced-choice preferences (SPEC-11) | SPECIFIED | Not implemented. Cold-start preference capture |
| Show driver cards (SPEC-12) | SPECIFIED | Schema and loader ready. No longer blocked: the card ships with an unconfirmed treatment plus a one-tap confirm that promotes a name to field_verified, so it works from day one and improves through use |
| Region and locale registry (SPEC-13) | SPECIFIED | Not implemented. Rising in priority: a city-onboarding pipeline needs it for bounding box, languages, currency and fare bands. Makes adding a city a row rather than a code change |
| Dietary model (SPEC-14) | DECIDED, DESCOPED | Not a feature. The spec is now a decision record: the app makes no dietary suitability claim, because no data source can support one. Ingredient facts stay as facts with a disclaimer. This is also how the halal-versus-pork hole closes |
| Trip checklist (SPEC-15) | SPECIFIED | Not implemented. Raw item text stays on the device; only a derived record syncs |
| Trust and verification (SPEC-17) | SPECIFIED | Not implemented, and it gates the three below. Owns attribute_claim plus the five display tiers: assert, hedge, ask, defer, refuse. No value crosses the API without its provenance, and the render layer refuses one that has none. Also owns attribute_registry, which carries the staleness horizon, the safety flag, the arrival-time flag and the deferral target for every attribute -- an attribute absent from it cannot be displayed at all. Confirmation expires: past its horizon a claim degrades one tier rather than vanishing |
| On-demand venue discovery (SPEC-18) | SPECIFIED | Not implemented. A traveller asks about where they are standing and the answer persists as a provisional venue, so the venue layer grows from real demand. Coordinate anchoring against OSM or Wikidata is mandatory before anything persists |
| Corpus mining (SPEC-19) | SPECIFIED | Not implemented. Extracts the operational knowledge no structured dataset carries, from openly licensed corpora only. This is the data source trip_edge never had. Google and TripAdvisor are excluded on licensing |
| City onboarding kit (SPEC-20) | SPECIFIED | Not implemented. Seeds a city's spine of 40 to 60 anchors, sourced identity first so provenance defaults to sourced rather than generated. SPEC-18 supplies the tail. validate_city refuses rather than warns |
| Client render contract (SPEC-22) | SPECIFIED | Not implemented, and it precedes every screen. Owns the mapping from SPEC-17's five tiers to five treatments, the interruption budget that SPEC-15 and SPEC-17 both draw on and neither can own, offline as a designed state rather than an error, and the type and script tokens. Can be built before SPEC-17's backend exists, since the envelope shape is already specified |
| OSM upstream contribution (SPEC-21) | DECIDED IN PRINCIPLE | Not scheduled, and not on the October path. A decision record rather than a spec: confirmed commodity facts go back to OpenStreetMap under the traveller's own account, never behavioural derivations, never model output, never subjective fields. Depends on SPEC-17 for field_verified claims. It also flags that our ODbL exposure is on the consuming side and already live via SPEC-20 |
| Money as a dimension (SPEC-23) | SPECIFIED | Not implemented. The engineering contract under VISION section 20, and roadmap concern 7. A band and an amount are different things and both are needed; no amount is storable without its currency; a band is meaningless until anchored to a region, which is what makes price tolerance portable between cities; transport cost belongs on trip_edge; budget is revealed from rejections rather than asked for, with a volunteered hard cap honoured exactly; amounts are SPEC-17 claims on a weeks-scale horizon and degrade to a band when stale. Depends on SPEC-13, SPEC-16 and SPEC-17 |

| Identity lifecycle (SPEC-24) | SPECIFIED | Not implemented, and the design is deliberately settled ahead of the build. Sign-in itself is nearly free because Supabase Auth owns the provider flow and security.py already verifies the token; the work is what happens to the anonymous history. Owns credential aliases, the anonymous-to-account merge, multi-device, and sign-out. Merge direction is fixed one way, which extends the upgrade-on-sight rule already live on identity_kind. Union rather than dedupe; tier and quota both resolve to the maximum, since taking the minimum makes sign-in a way to refill the daily reroute allowance |
| Ask Anything surface (SPEC-25) | SPECIFIED | Not implemented. Free text reaches the engine today only through trip/event, which requires a trip_id, so a search box outside a trip has nowhere to post and SPEC-18's central scenario cannot be asked at all. Owns one endpoint with the trip optional, a closed intent set that routes only to capabilities that already exist, and cost bounds applied before the model call rather than around it. Every answer is a SPEC-17 envelope: there is no prose channel, which is what stops the box becoming an ungrounded chatbot. Offline it answers from cache or refuses at once, and never queues |
| Home surface (SPEC-26) | SPECIFIED | Not implemented. get_active_trips already exists in the service layer with no route exposing it, so a returning user cannot be shown their own trips -- the gap is one route, not a subsystem. Also owns a single self-contained home aggregate that renders offline, the designed empty state, and a trip creation path requiring destination and dates only. Gated on SPEC-13 for region validity, since geo_region is still an unconstrained string |
| App lifecycle and data rights (SPEC-27) | SPECIFIED | Not implemented. The three consumer obligations with no owner: push transport with tokens that survive the SPEC-24 merge and delivery through the SPEC-22 interruption budget enforced server-side, deletion and export under DPDP and GDPR, and a minimum supported client that blocks writes but never reads. States the position that raw signals are deleted while non-identifying derived aggregates survive |

Migration numbers are assigned when a spec is implemented, not when it is
written. SPEC-11, SPEC-13, SPEC-14 and SPEC-15 each claimed a number, and the
numbers were taken by other work while they sat unimplemented.

## What is Next (Priority Order)

### Interim (laptop unavailable until ~Aug 15)

0. Relocate VALID_DISH_CONTAINS to config/dietary.py (R5). Pure refactor, no
   schema dependency, no live data. Brief: docs/briefs/GENIE_RELOCATE_VALID_DISH_CONTAINS.md.
   Genie executes; lands via PR.

### October path (forcing function: Laos field test, Oct 2)

Success means an installable build whose engine knows a real trip anchored on
real flight and hotel bookings, and whose driver card works without
connectivity. Re-cut Aug 14 after finding that CONSUMER_SURFACE_ROADMAP and
PROJECT_STATUS disagreed on SPEC-04, and that SPEC-04 mostly duplicated
SPEC-02 plus SPEC-12.

1. Device day -- blocked on the laptop only. Runnable brief:
   docs/briefs/DEVICE_DAY.md. Export Dubai to data/dubai_uae.json and push it
   before any migration apply. Then dump/diff the live schema (0011 dual
   name_local / names_local gate), apply 0011 to 0018, re-load Laos, run
   pytest with TB_SUPABASE_URL set, and record the live checks
   (price_band, AED magnitudes, pg_description, hybrid_venue_search).
2. SPEC-09 client half: UUID on first launch, secure storage, Anonymous
   header, drop TB_DEBUG_USER_ID. Server half is done; this is what gates a
   tester build.
3. SPEC-22 client render contract, before any screen. Envelope shape is
   already specified; stub the source on the client if SPEC-17 backend is
   not ready.
4. SPEC-12 driver card UI with one-tap confirm, plus name_confirmed and
   driver_card_shown in one migration. Renders from SPEC-02 cache_place.
5. SPEC-10 booking anchors (manual floor plus import path as specified).
   This is what makes "full context" true for the field test.
6. SPEC-04 October slice only: <=2-tap rescue entry to the hotel address
   card, offline/cold-boot, reusing the SPEC-12 treatment against the
   accommodation node. Not the full vault.

### After the field-test spine (still important, not Oct-critical)

7. Give observed_duration_minutes a writer from arrival signals on sync.
8. Retire the dietary suitability claim (SPEC-14). Closes the
   halal-versus-pork hole by removing the claim.
9. SPEC-17 trust and verification -- gates SPEC-18/19/20; behind the
   field-test installable app on purpose.
10. reroute_rejected plus swap sheet UI -- last unwired behavioural signal.
11. Full SPEC-04 remainder (cache_vault, passes, emergency grid, phrase
    packs) if still wanted.
12. Consumer surface per docs/CONSUMER_SURFACE_ROADMAP.md (SPEC-26, then
    SPEC-25, then SPEC-27; SPEC-24 design settled, build later).
13. Swappable LLM provider -- no owning spec yet; next free number. Every
    intelligent path is one hosted vendor today.

Export the Dubai rows before applying anything. A rebuild from migrations
without that export silently loses 16 venues. There is no DB snapshot
outside the hosted project; that is why device-day Step 2 commits
data/dubai_uae.json before Step 4.

The one task that cannot be done by an agent is judging whether a
transliterated venue name is what the signage actually says. A script test
catches Chinese where Lao belongs; it cannot catch a wrong vowel inside
otherwise correct Lao, and two such errors are known to exist. That is why the
driver card asks the traveller to confirm rather than asserting.

## Known Risks and Open Issues

Full detail is in docs/AWAITING_VERIFICATION.md.

| Issue | Severity | Detail |
|-------|----------|--------|
| Anonymous data has no path into an account, and signal sits outside referential integrity | Medium | SPEC-09 starts accumulating trip_states, event_log and signal rows under a device UUID that belongs to a device rather than a person. Until SPEC-24 exists, the first sign-in strands all of it, and from the user's side that looks like an app that lost their trip. The schema makes it sharper: trip_states.user_id and event_log.user_id are UUID REFERENCES user_tiers, while signal.user_id is TEXT with no foreign key and no type match, so the table holding the asset is the one table outside the constraint system. Neither a merge nor a SPEC-27 deletion can rely on a cascade, and nothing will complain when a future table is missed -- which is why both specs walk the schema instead of keeping a list. The engineering does not get harder with time; the data does |
| observed_duration_minutes has no writer | Medium | The column exists and is honestly documented as starting empty, but nothing populates it. It cannot be computed when a trip is saved, only derived from arrival signals on sync, so the transition data the convenience layer depends on is not accumulating. This is the last open defect from the SPEC-16 work |
| The five Supabase tests have never run | Medium | tests/test_supabase_integration.py skips without TB_SUPABASE_URL, and no run has ever had it set. Every claim about the Supabase write path rests on FakeClient doubles. R8 treats a permanent skip as a finding, and this is the largest one. Run the suite with credentials on the next device day |
| Non-Laos local dish names remain unbackfilled | Low | 0015's names_local backfill is correctly scoped to the three Laos regions, so any Dubai dish carrying a name_local keeps a null names_local rather than a wrong language tag. That is the right trade, but it leaves a second pass owed once the Dubai rows are exported and their language confirmed |
| deploy fails: there is no deployment target | Medium | ci.yml chains lint, test, build and deploy, each needing the one before, and lint failed on every run as far back as the retained history, so build and deploy had never executed once in the life of this repository. Both ran for the first time on 8ed6c16. build passed and pushed an image to the container registry, which is the first artifact this project has ever produced. deploy failed after one second at the Railway step, which needs a RAILWAY_TOKEN secret and a service named travel-buddy-api; the health check reads a PRODUCTION_URL secret. Nothing here is a regression -- it is scaffolding written early and never once exercised. Resolved by gating: deploy now requires workflow_dispatch, so main stays green and deploying becomes a deliberate act from the Actions tab once a target exists. build still runs on every push to main, so the image is proven continuously and only the release step is manual. Left ungated it would have made main permanently red, which is the exact condition that let lint stay broken and unnoticed for a week |
| Signal provenance was silently unwritten until today | Low | _compute_provenance computed clock skew and its return was discarded, while both backends defaulted provenance to a constant. So clock_skew_seconds was never persisted for any signal and SPEC-02 Part C was unmet in the live write path. Fixed and guarded by a test that drives the ingest endpoint rather than the storage layer. Recorded because the gap was invisible for months: nothing failed, the column had a default, and the only symptom was analytics that could not exist |
| The scheduler is money-blind | Medium | services/scheduler.py contains no reference to price, cost, budget or fare, and no model carries traveller spend capacity, so affordability cannot be ranked on at all. The only price in config is Stripe subscription pricing, which is our revenue rather than the traveller's spend. Specified as SPEC-23 and roadmap concern 7; the cost of delay compounds with venues, regions and trips simultaneously. The venues_rag.price_band half of this row was closed by 0017 |
| The price_band vocabulary is declared in three places and linked by one test | Low | 0017 constrains venues_rag.price_band, which was the last unconstrained one, but a CHECK duplicates the taxonomy rather than referencing it. What actually binds them is test_venues_rag_price_band_check_matches_taxonomy, which parses both files and compares sets. That guard is hardcoded to one filename, so a fourth price_band CHECK added later is unguarded, and 0005 still declares the superseded vocabulary including premium. The claim in 0017 that any future table is now taxonomy-aligned is not true as written |
| price_band CHECK is added but not validated | Low | 0015 adds the CHECK as NOT VALID so it cannot abort, which means existing rows are never checked against it. New and updated rows are. The VALIDATE CONSTRAINT statement is present but commented out; run it after reading the distinct live price_band values |
| node_id carries 32 bits of entropy | Low | generate_node_id truncates a UUID to 8 hex characters, and node_id is a primary key with foreign key references from trip_edge. Collision probability is not negligible at scale. Both generators now live in models/ids.py, so widening it is a one-line change plus a backfill decision |
| The ASCII convention for code is enforced narrowly, by design | Low | Two guards landed in 1c9988f rather than a blanket file scan. SQL is checked only inside COMMENT ON bodies, which is where non-ASCII reaches the database, and a companion test fails if any COMMENT ON statement escapes the extraction regex, so dollar-quoting cannot silently bypass it. Python is checked in comments and docstrings via tokenize and ast, with string literals exempt because a degree sign in a temperature format is correct code. The narrow guard immediately found an em-dash in an applied migration that a survey of the same files had missed. Remaining exposure: .dart is not covered, and non-ASCII in Python string literals is permitted by choice |
| Live schema contains manual edits of unknown extent | High | Loads have been succeeding against columns no migration declared, so somebody added them by hand. PostgREST rejects writes to columns absent from its schema cache, so this is not a REST-layer quirk. Migration 0011 must not be applied before a dump and diff: if a hand-made name_local TEXT exists, ADD COLUMN IF NOT EXISTS names_local JSONB adds a second empty column and leaves the populated one unread |
| Dubai venue data has no source file | High | data/ holds only the Laos files. The 16 Dubai venues exist as rows in the hosted database and nowhere else, so a rebuild from migrations loses them. Export to version control before any rebuild |
| OSM licence position unexamined | Medium | SPEC-19 mines OpenStreetMap and SPEC-20 seeds venues_rag from it, which plausibly makes venues_rag a derivative database under ODbL and attaches share-alike to it if it is ever distributed. Recommendations generated on top are most likely a produced work, needing attribution only. Nobody qualified has looked at either question. Recorded in the SPEC-21 decision record; it needs advice before a city is onboarded from OSM at scale, not after |
| The dietary safety layer has no data source | RESOLVED BY DESCOPING | In OSM, diet:halal covers 20 of 6611 central Bangkok POIs and diet:vegetarian about two percent; Dubai is the best case at six and seven percent. A safety filter with no trustworthy input converts caution into misplaced confidence, so the claim is retired rather than sourced. See the SPEC-14 decision record |
| halal plus pork passes the allergen check | High until the claim is retired | No LABEL_EXCLUDES_ALLERGENS rule for halal, so a pork-serving venue passes a halal check. The fix is to stop making the claim, not to add the rule -- adding it would make the answer trustworthy-looking on data that cannot support it. Live until the retirement lands |
| Most localized names remain unverified | Medium | Forty-eight of 58 stay source=generated. Two known errors are a wrong vowel inside otherwise valid Lao, which no codepoint guard can detect. The driver card's confirm affordance is the mitigation |
| Lao order phrase may say fry, not spicy | Medium | The papaya salad phrase reads bo phat lai, not bo phet lai -- stir-fry rather than spicy, one missing vowel. Needs a native speaker, not a script check. Three of four hot dishes carry no moderating phrase at all, and the raw-meat laap has no cooked-request phrase |
| opening_hours null on all Laos venues | Medium | The loader writes opening_hours_structured correctly; the data has simply never been re-loaded since |
| hybrid_venue_search geo_region param | Medium | supabase_service passes a geo_region filter the RPC in 0001 does not declare. Verify against the live function |
| price_local units documented, AED rows still suspect | Medium | 0015 states the rule: minor units per the ISO 4217 exponent, so LAK at exponent 0 means 35000 = 35000 LAK and AED at exponent 2 means 4500 = 45.00 AED. The 0009 comment's "45 AED" example was ambiguous, so existing Dubai dish prices may be off by 100x either way. Device check against the live rows; do not backfill blindly |
| Raw-safety guard keys off English prose | Low | The guard that flags an uncooked dish looks for the word raw in the description, so rewording a description silently disables a safety check. Key it off a structured field |
| seniors overcorrected | Low | Set on 40 of 58 venues, roughly two thirds, so it cannot discriminate. mobility_limited is 17 of 58, which is plausible rather than overcorrected -- an earlier version of this table attributed the two-thirds figure to the wrong tag |
| Vientiane has zero massage_spa | Low | Suspect. This was reported by a warning function that was broken until recently, so re-check it against the data rather than trusting the earlier report |
| VALID_DISH_CONTAINS in the wrong file | Low | Lives in load_dish_glossary.py, belongs in config/dietary.py (R5). Interim Genie brief: docs/briefs/GENIE_RELOCATE_VALID_DISH_CONTAINS.md |
| Full Offline Vault was over-scoped for October | Low | Resolved in docs Aug 14: SPEC-04 shrunk to a thin hotel-card rescue entry; venue card is SPEC-12 on SPEC-02 cache. Left here so an old CONSUMER_SURFACE quote is not re-elevated |

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
