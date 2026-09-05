# Travel Buddy -- Project Status

> Current state of the codebase. For commit history use `git log`.
> For the device-verification queue see docs/AWAITING_VERIFICATION.md.
> For engineering rules see docs/ENGINEERING_RULES.md.
> For how the people and agents around the code work, see docs/WAYS_OF_WORKING.md.
> Read that one before your first review or brief, not after.
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
  hierarchy. Signal emission is wired for most but not all registered types.
  Hearts persist across process death (verified Aug 30 on Windows).
  `session_start` emits from the app lifecycle (SPEC-30, `f8349a8`).
  Sync Status must still await `syncOnce()` before reading counts.
- Migrations 0011 to 0018 are applied on the hosted database (device day
  2026-08-17, Supabase SQL editor). 0011 was gated on a live OpenAPI schema
  dump (no name_local dual-column conflict). 0015/0017 CHECKs remain NOT
  VALID until a deliberate VALIDATE after distinct-value review.
- Every file under data/ is ASCII-escaped, and a guard enforces it. Use
  scripts/format_venue_json.py to get a readable copy for curation and to
  re-escape on the way back in.
- Test health: run `pytest -q -ra`. Counts are deliberately not recorded here
  (R16). The live-database tests in tests/test_supabase_integration.py skip
  when TB_SUPABASE_URL is unset; with credentials they ran green on device day
  2026-08-17. Any unexpected skip is a finding, not a pass (R8).

## Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| Supabase persistence | LIVE | db_provider auto-resolves; falls back to in-memory |
| Migrations 0001-0010 | APPLIED | 0005 entity_ref generalization, 0007 RLS, 0008 hours JSONB, 0009 dish price, 0010 glossary |
| Migration 0011 | APPLIED (device day 2026-08-17) | Eight additive columns; OpenAPI gate cleared (no name_local dual column) |
| Migration 0012 venue_external_id | APPLIED (device day 2026-08-17) | Maps a venue to Wikidata, OSM, Google and Foursquare identifiers, unique on (source, external_id). Roadmap concern 2 |
| Migration 0013 taxonomy_term | APPLIED (device day 2026-08-17) | Versions the controlled vocabulary across ten taxonomies, seeded from the venue and dish data. Roadmap concern 6 |
| Migration 0014 itinerary normalisation | APPLIED (device day 2026-08-17) | Creates trip_node and trip_edge. node_id and edge_id are TEXT, which matches the 8-character hex IDs the application generates |
| Migration 0015 drift fixes | APPLIED (device day 2026-08-17) | price_band CHECK NOT VALID; names_local backfill; currency_code; embedding_model. VALIDATE deferred |
| Migration 0016 comment fixes | APPLIED (device day 2026-08-17) | Comments only; confirm pg_description ASCII in Step 7 |
| Migration 0017 venues_rag price_band | APPLIED (device day 2026-08-17) | NOT VALID CHECK; VALIDATE deferred until distinct-value read |
| Migration 0018 anonymous identity | APPLIED (device day 2026-08-17) | identity_kind on user_tiers |
| Venue loader | REPAIRED, CARRIES EVERY FIELD | Pure ASCII, vocabulary restored, geo_region inferred from the file wrapper. Payload built once in build_venue_record; insert and update derive from it so they cannot drift apart |
| Loader payload guard | DONE | A test asserts build_venue_record's key set equals VENUES_RAG_WRITE_COLUMNS, and build_dish_record does the same for venue_dish against VENUE_DISH_WRITE_COLUMNS. The earlier guards watched the declaration only, which is how four fields were dropped while the suite stayed green |
| External-id writer | DONE | upsert_venues writes venue_external_id for every venue carrying a verified name reference, and the test drives upsert_venues rather than the helper, which is the distinction that let the first attempt land as dead code |
| Localized names | PARTLY VERIFIED | Ten of 58 venues carry a name confirmed against Wikidata or OSM, with source and ref recorded. Three classes of wrong-script token are fixed. The remaining 48 stay source=generated |
| Curation round-trip | DONE | scripts/format_venue_json.py converts between the ASCII-escaped repo form and a readable UTF-8 copy under curation/, which is gitignored. Byte-identical round-trip is asserted |
| Signal capture (SPEC-01) | DONE | All registered types accepted, both backends |
| Offline queue (SPEC-02) | PARTIAL | SQLite outbox, sync engine and crash recovery are done. PR #23 (`dab16c0`) added resetAuthHalted() and HALTED (401). Hearts survive app kill (Aug 30 Windows). Sync Status still does not await `syncOnce()` before reading counts |
| Party context (SPEC-03) | DONE | Server-side stamping, both backends, migration 0003 applied |
| Observability (SPEC-05) | DONE | Ring buffer, request IDs, debug endpoint |
| Signal registry (SPEC-06) | DONE | models/signal_types.py plus drift test |
| Signal emission (SPEC-07) | IMPLEMENTED | SwapSheet wired: tap Swap opens sheet with real venue search, confirm sends swap_activity + reroute_accepted, dismiss sends reroute_rejected. Remaining: dish_loved, dish_ordered UI |
| Laos curation (SPEC-08) | DONE | 58 venues curated including Lao script. The wrong-script contamination is fixed: appended Chinese, Thai spelling of a Lao word, and a Thai-style consonant cluster |
| arrival_delta derivation | DONE | Server-derived from visited_confirmed vs scheduled_start |
| Docs hygiene guard | DONE | tests/test_docs_hygiene.py walks every markdown file outside build and vendor directories, and the SPEC-reference check also scans .py and .sql. Known non-ASCII files are allowlisted; the list may only shrink. The ASCII check itself still covers markdown only |
| Data format guard | DONE | Every data/ file is ASCII by byte count, venue and glossary files round-trip byte-identically, and Lao-script fields are checked for foreign script |
| Offline vault (SPEC-04) | DONE (October slice) | PR #22 (`b7e10c3`) + PR #23 (`dab16c0`). <=2-tap hotel rescue entry to DriverCardScreen, offline itinerary cache fallback in ItineraryController.load(), robust hotel matching (villa/guesthouse), pre-caching hotel place data in cache_place, honest empty state. Full vault post-field-test -- see SPEC-04 |
| Anonymous identity (SPEC-09) | DONE (client + server) | Client half landed PR #16 (`7173a3f`): UUID v4 in flutter_secure_storage, Anonymous header, TB_DEBUG_USER_ID removed. Server half already verified. Record any remaining Anonymous E2E gap explicitly; the laptop is available |
| Itinerary normalisation (SPEC-16) | IMPLEMENTED | Decompose and compose land in services/itinerary_normaliser.py, dual-write in both backends, round-trip equality asserted, wire format unchanged. node_id is stable across reschedules via state_json and now comes from models/ids.py. SPEC-30 (`f8349a8`) writes `trip_edge.observed_duration_minutes` from consecutive arrivals |
| Booking anchors (SPEC-10) | PARTIAL (create plus edit/delete) | PR #20 (`f6328e9`) plus PR #37 (`364d873`). Immovable locked nodes, booking metadata, parser and AddBookingSheet. Windows Sep 4 verified notes, edit, and delete. Daily hotel anchor and preceding-evening flight rules remain |
| Forced-choice preferences (SPEC-11) | SPECIFIED | Not implemented. Cold-start preference capture |
| Show driver cards (SPEC-12) | DONE (October slice) | Full-screen offline card from SQLite cache_place, FactView assert/ask/refuse tiers, geoRegion-threaded native script, driver_card_shown/name_confirmed signals. Dubai airplane behavior was verified Aug 27-28: no fare and no screenshot copy. No Fair Fare until sourced; Windows `geo:` hand-off failed, so keep small last-resort coordinates. Migration 0023 (unapplied) carries localized fields through live venue search |
| Region and locale registry (SPEC-13) | SPECIFIED | Not implemented. Rising in priority: a city-onboarding pipeline needs it for bounding box, languages, currency and fare bands. Makes adding a city a row rather than a code change |
| Dietary model (SPEC-14) | IMPLEMENTED | Retirement landed. The app makes no dietary suitability claim. suitable_for is stripped from API responses, never presented or filtered on. Ingredient facts stay as facts with a food disclaimer at the point of the recommendation. halal-versus-pork risk closed |
| Trip checklist (SPEC-15) | SPECIFIED | Not implemented. Raw item text stays on the device; only a derived record syncs |
| Trust and verification (SPEC-17) | PARTIAL (disclosure slice) | Sponsored search disclosure (decision 15) implemented: GET /venues/search returns flat results with server-derived sponsored_boost_applied; SwapSheet labels boosted results and explains ranking influence. Full SPEC-17 (attribute_claim, display tiers, attribute_registry, staleness degradation) remains unimplemented and still gates SPEC-18/19/20 |
| On-demand venue discovery (SPEC-18) | SPECIFIED | Not implemented. A traveller asks about where they are standing and the answer persists as a provisional venue, so the venue layer grows from real demand. Coordinate anchoring against OSM or Wikidata is mandatory before anything persists |
| Corpus mining (SPEC-19) | SPECIFIED | Not implemented. Extracts the operational knowledge no structured dataset carries, from openly licensed corpora only. This is the data source trip_edge never had. Google and TripAdvisor are excluded on licensing |
| City onboarding kit (SPEC-20) | SPECIFIED | Not implemented. Seeds a city's spine of 40 to 60 anchors, sourced identity first so provenance defaults to sourced rather than generated. SPEC-18 supplies the tail. validate_city refuses rather than warns |
| Client render contract (SPEC-22) | DONE (October slice) | PR #17 squash-merged as `1b9b1b3`. Envelope widget, five treatments, interruption budget, offline state, PromptDismissAdapter -> SignalService.emit(prompt_dismissed). Font cmap, ARB wiring, and screen migration deferred. Migration 0019 unapplied on live DB until laptop |
| OSM upstream contribution (SPEC-21) | DECIDED IN PRINCIPLE | Not scheduled, and not on the October path. A decision record rather than a spec: confirmed commodity facts go back to OpenStreetMap under the traveller's own account, never behavioural derivations, never model output, never subjective fields. Depends on SPEC-17 for field_verified claims. It also flags that our ODbL exposure is on the consuming side and already live via SPEC-20 |
| Money as a dimension (SPEC-23) | SPECIFIED | Not implemented. The engineering contract under VISION section 20, and roadmap concern 7. A band and an amount are different things and both are needed; no amount is storable without its currency; a band is meaningless until anchored to a region, which is what makes price tolerance portable between cities; transport cost belongs on trip_edge; budget is revealed from rejections rather than asked for, with a volunteered hard cap honoured exactly; amounts are SPEC-17 claims on a weeks-scale horizon and degrade to a band when stale. Depends on SPEC-13, SPEC-16 and SPEC-17 |

| Identity lifecycle (SPEC-24) | SPECIFIED | Not implemented, and the design is deliberately settled ahead of the build. Sign-in itself is nearly free because Supabase Auth owns the provider flow and security.py already verifies the token; the work is what happens to the anonymous history. Owns credential aliases, the anonymous-to-account merge, multi-device, and sign-out. Merge direction is fixed one way, which extends the upgrade-on-sight rule already live on identity_kind. Union rather than dedupe; tier and quota both resolve to the maximum, since taking the minimum makes sign-in a way to refill the daily reroute allowance |
| Ask Anything surface (SPEC-25) | PARTIAL (trip-scoped October slice) | The itinerary composer and per-trip home entry use existing trip chat. One-stop cancel/swap are structural; cancel is a skip, not a swap, as of SPEC-29. Broad mutations refuse. No add-from-chat control; near-me uses default Dubai coordinates. Trip-optional ask, pre-model budgets, SPEC-17 envelopes, discovery and offline answer contract remain |
| Home surface (SPEC-26) | IMPLEMENTED (snapshot) | GET /trips now returns featured_trip: active trip (or earliest upcoming) with actionable stop (no state_json, no full nodes). Dart HomeSnapshot parses and caches it. Home renders Now/Up next card above trip list. Offline cache renders same card with cache age. Full SPEC-22 migration remains |
| App lifecycle and data rights (SPEC-27) | SPECIFIED | Not implemented. The three consumer obligations with no owner: push transport with tokens that survive the SPEC-24 merge and delivery through the SPEC-22 interruption budget enforced server-side, deletion and export under DPDP and GDPR, and a minimum supported client that blocks writes but never reads. States the position that raw signals are deleted while non-identifying derived aggregates survive |
| Trip inspiration (SPEC-28) | DECIDED, NOT SCHEDULED | Opt-in, delayed, region-level public trip snapshots as inspiration. No live people/location, DMs or comments in v1. Requires identity, deletion/export and moderation gates |
| Context alerts (SPEC-29) | DONE (phase 1) | PR #25 squash-merged as `aedbc03`. OpenWeather evidence is matched to upcoming nodes, cached by identity and shown with provenance. Alerts never mutate or consume reroute quota. Synthetic transit is not user copy; cancel preserves position and locked cancel returns 409 before quota. Watcher/push phase not started |
| Retention instrumentation (SPEC-30) | DONE | PR #32 (`f8349a8`) added `session_start` and the `trip_edge` observed-duration writer. PR #34 (`83c825f`) added durable node outcomes, active/past confirmation UI, outcome-aware targeting, and explicit cancel confirmation. Flutter CI and owner Windows full suite green |
| Date-scoped itinerary and stay rescue (SPEC-31) | PARTIAL | Grouping under date headers is on main (PR #36, Windows Sep 4 6A). Stay-rescue selection (6C) was not device-tested. No `day_index`, timezone conversion, wire, schema, scheduler, or `trip_stay` change |
| Real Laos trip creation (SPEC-32) | IMPLEMENTED (this branch) | Catalog-backed one-city create for Dubai and the three Laos codes. Device-verify a Laos city remains |

Migration numbers are assigned when a spec is implemented, not when it is
written. SPEC-11, SPEC-13, SPEC-14 and SPEC-15 each claimed a number, and the
numbers were taken by other work while they sat unimplemented.

## What is Next (Priority Order)

### October path (forcing function: Laos field test, Oct 2)

Interim R5 relocate of VALID_DISH_CONTAINS landed in PR #15 (d061222). Device
day is closed and the Windows laptop ran the product matrix on Aug 27-28.
Remaining device work must be named explicitly: unapplied migrations
(0023 and any earlier unapplied except 0024 if already applied on hosted),
Profile/Skip exact errors, and any unrecorded Anonymous E2E. Durable hearts
passed on Windows Aug 30.

Success means an installable build whose engine knows a real trip anchored on
real flight and hotel bookings, and whose driver card works without
connectivity. Re-cut Aug 14 after finding that CONSUMER_SURFACE_ROADMAP and
PROJECT_STATUS disagreed on SPEC-04, and that SPEC-04 mostly duplicated
SPEC-02 plus SPEC-12.

1. Device day -- **CLOSED** 2026-08-17. Brief: docs/briefs/DEVICE_DAY.md.
   Dubai raw dump 6bfa1c6; migrations 0011-0018 applied; Laos reloaded;
   live pytest ran green with TB_SUPABASE_URL (five Supabase integration
   tests included); dubai_dishes=0. Loader-valid
   data/dubai_uae.json remains a follow-up (not Oct-spine blocking).
2. SPEC-09 client half -- **DONE** PR #16 (`7173a3f`). Record any remaining
   `TB_ALLOW_ANONYMOUS=true` E2E gap explicitly; laptop access is no longer the
   blocker.
3. SPEC-22 client render contract -- **DONE** PR #17 (`1b9b1b3`). October
   slice only; SPEC-17 backend still stubbed. Migration 0019 remains unapplied
   unless separately recorded; Flutter verification is tracked by current CI
   and the Windows runbook.
4. Itinerary signal, auth-gate, and Flutter CI -- **DONE** PR #18
   (`ce8fedb`). Flutter job green; owner laptop `flutter analyze
   --no-fatal-infos` (infos only) and `flutter test` green on `d7eb853`.
   Planning-agent handoff: docs/HANDOFF_PLANNING_AGENT.md.
5. SPEC-12 driver card UI with one-tap confirm -- **DONE** PR #19
   (`a2da64a`). Full-screen offline card on FactView / ConfirmAffordance /
   cache_place, driver_card_shown & name_confirmed signals (migration 0020
   in repo, unapplied live).
6. SPEC-10 booking anchors -- **DONE** PR #20 (`f6328e9`). Immovable
   locked nodes on timeline, scheduler hard conflict rules, on-device text
   extractor, AddBookingSheet, and booking_added signal in migration 0021
   (in repo, unapplied live).
7. SPEC-04 October slice: <=2-tap rescue entry to hotel address card &
   offline itinerary cache -- **DONE** PR #22 (`b7e10c3`). Offline itinerary
   reads from SQLite cache_trip, hotel rescue sheet / direct driver card
   navigation, pre-caching hotel place data.
   Post-spine hardening merged in PR #23 (`dab16c0`): geoRegion threading
   to driver card (native script resolves; no fare is claimed), authHalted reset
   and UI status card, and robust hotel matching.
   **All 7 items on the October field-test spine are complete & hardened!**

### Pre-field-test instrumentation gate (added Aug 2026)

The seven-item spine proves the *engine* works on the trip. SPEC-30 is complete:
PR #32 records `session_start` and observed edge duration; PR #34 adds durable
node outcomes and explicit cancel-target confirmation. That is instrumentation,
not a validated retention curve: one field-test trip still cannot prove
Seed-shaped cohorts.

- **Sponsored-placement disclosure (SPEC-17 decision 15).** Sponsored boost is
  live in the ranker with no client disclosure, and Pro is sold as removing it.
  Decide and land the disclosure surface before adding any affiliate revenue; it
  gates the monetization path in VISION section 9. Not code-heavy.

### After the field-test spine (still important, not Oct-critical)

8. SPEC-32 catalog-backed Laos create (this branch), then remaining stay-rescue
   product cut and multi-night hotel UI.
9. Retire the dietary suitability claim (SPEC-14). Closes the
   halal-versus-pork hole by removing the claim.
10. SPEC-17 trust and verification -- gates SPEC-18/19/20; behind the
   field-test installable app on purpose.
11. reroute_rejected plus swap sheet UI -- last unwired behavioural signal.
12. Full SPEC-04 remainder (cache_vault, passes, emergency grid, phrase
    packs) if still wanted.
13. Finish the consumer slices already on the October path: date-scoped
    itinerary and bookings, trip-less Ask and
    the richer Home aggregate. SPEC-27 follows; SPEC-24 design is settled.
14. Swappable LLM provider -- no owning spec yet; next free number. Every
    intelligent path is one hosted vendor today.

Export the Dubai rows before applying anything. A rebuild from migrations
without that export silently loses 16 venues. Step 2 durability is met by
data/dubai_uae_raw_snapshot.json (6bfa1c6). A loader-valid dubai_uae.json
is still a follow-up, not a migration blocker.

The one task that cannot be done by an agent is judging whether a
transliterated venue name is what the signage actually says. A script test
catches Chinese where Lao belongs; it cannot catch a wrong vowel inside
otherwise correct Lao, and two such errors are known to exist. That is why the
driver card asks the traveller to confirm rather than asserting.

## Known Risks and Open Issues

Full detail is in docs/AWAITING_VERIFICATION.md.

| Issue | Severity | Detail |
|-------|----------|--------|
| reroute_accepted.replacement_ref is inverted | Closed PR #18 (`ce8fedb`) | Client helper replacementRefForSwap matches node_id and changed venue key. Production `_swap` calls it |
| Supabase session gate softlocks the app | Closed PR #18 (`ce8fedb`) | app_router calls redirectForAuth; anonymous device needs no session. Owner E2E with dart-defines still in LAPTOP_VERIFY Step 8b |
| Anonymous data has no path into an account, and signal sits outside referential integrity | Medium | SPEC-09 starts accumulating trip_states, event_log and signal rows under a device UUID that belongs to a device rather than a person. Until SPEC-24 exists, the first sign-in strands all of it, and from the user's side that looks like an app that lost their trip. The schema makes it sharper: trip_states.user_id and event_log.user_id are UUID REFERENCES user_tiers, while signal.user_id is TEXT with no foreign key and no type match, so the table holding the asset is the one table outside the constraint system. Neither a merge nor a SPEC-27 deletion can rely on a cascade, and nothing will complain when a future table is missed -- which is why both specs walk the schema instead of keeping a list. The engineering does not get harder with time; the data does |
| observed_duration_minutes writer | Closed PR #32 (`f8349a8`) | Consecutive arrivals update `trip_edge.observed_duration_minutes`. Dual-write preserves the value. Transport cost on the same table is still unwritten (SPEC-23) |
| The five Supabase tests have never run | Closed Aug 17 2026 | Live device-day pytest with TB_SUPABASE_URL set; tests/test_supabase_integration.py included. Run pytest -q -ra to confirm |
| Non-Laos local dish names remain unbackfilled | Low | 0015's names_local backfill is correctly scoped to the three Laos regions, so any Dubai dish carrying a name_local keeps a null names_local rather than a wrong language tag. That is the right trade, but it leaves a second pass owed once the Dubai rows are exported and their language confirmed |
| deploy fails: there is no deployment target | Medium | ci.yml chains lint, test, build and deploy, each needing the one before, and lint failed on every run as far back as the retained history, so build and deploy had never executed once in the life of this repository. Both ran for the first time on 8ed6c16. build passed and pushed an image to the container registry, which is the first artifact this project has ever produced. deploy failed after one second at the Railway step, which needs a RAILWAY_TOKEN secret and a service named travel-buddy-api; the health check reads a PRODUCTION_URL secret. Nothing here is a regression -- it is scaffolding written early and never once exercised. Resolved by gating: deploy now requires workflow_dispatch, so main stays green and deploying becomes a deliberate act from the Actions tab once a target exists. build still runs on every push to main, so the image is proven continuously and only the release step is manual. Left ungated it would have made main permanently red, which is the exact condition that let lint stay broken and unnoticed for a week |
| Signal provenance was silently unwritten until today | Low | _compute_provenance computed clock skew and its return was discarded, while both backends defaulted provenance to a constant. So clock_skew_seconds was never persisted for any signal and SPEC-02 Part C was unmet in the live write path. Fixed and guarded by a test that drives the ingest endpoint rather than the storage layer. Recorded because the gap was invisible for months: nothing failed, the column had a default, and the only symptom was analytics that could not exist |
| The scheduler is money-blind | Medium | services/scheduler.py contains no reference to price, cost, budget or fare, and no model carries traveller spend capacity, so affordability cannot be ranked on at all. The only price in config is Stripe subscription pricing, which is our revenue rather than the traveller's spend. Specified as SPEC-23 and roadmap concern 7; the cost of delay compounds with venues, regions and trips simultaneously. The venues_rag.price_band half of this row was closed by 0017 |
| Sponsored placement is undisclosed in the client | Medium, gates affiliate | database_service.py adds bid_weight * sponsored_boost_multiplier (0.15) to a venue's similarity score, seed venues ship is_sponsored=True, cost_tracker prices a sponsored_impression, and payment_service sells "No sponsored results" as a paid benefit -- so the free tier ranks paid venues higher and nothing in the client says so. This is a live contradiction with "trust is the product" (VISION section 10). Decision: disclose sponsored contribution at render and make it inspectable before any affiliate revenue is added. Recorded as SPEC-17 decision 15 and in the VISION section 9 monetization rewrite. Not a regression; it has been latent since 0001 |
| The price_band vocabulary is declared in three places and linked by one test | Low | 0017 constrains venues_rag.price_band, which was the last unconstrained one, but a CHECK duplicates the taxonomy rather than referencing it. What actually binds them is test_venues_rag_price_band_check_matches_taxonomy, which parses both files and compares sets. That guard is hardcoded to one filename, so a fourth price_band CHECK added later is unguarded, and 0005 still declares the superseded vocabulary including premium. The claim in 0017 that any future table is now taxonomy-aligned is not true as written |
| price_band CHECK is added but not validated | Low | 0015 adds the CHECK as NOT VALID so it cannot abort, which means existing rows are never checked against it. New and updated rows are. The VALIDATE CONSTRAINT statement is present but commented out; run it after reading the distinct live price_band values |
| node_id carries 32 bits of entropy | Low | generate_node_id truncates a UUID to 8 hex characters, and node_id is a primary key with foreign key references from trip_edge. Collision probability is not negligible at scale. Both generators now live in models/ids.py, so widening it is a one-line change plus a backfill decision |
| The ASCII convention for code is enforced narrowly, by design | Low | Two guards landed in 1c9988f rather than a blanket file scan. SQL is checked only inside COMMENT ON bodies, which is where non-ASCII reaches the database, and a companion test fails if any COMMENT ON statement escapes the extraction regex, so dollar-quoting cannot silently bypass it. Python is checked in comments and docstrings via tokenize and ast, with string literals exempt because a degree sign in a temperature format is correct code. The narrow guard immediately found an em-dash in an applied migration that a survey of the same files had missed. Remaining exposure: .dart is not covered, and non-ASCII in Python string literals is permitted by choice |
| Live schema contains manual edits of unknown extent | Low | 0011 applied after OpenAPI dump; no name_local dual-column. Residual hand-edit risk is historical; new columns are migration-declared |
| Dubai venue data has no loader-valid source file | Medium | Durability: dubai_uae_raw_snapshot.json (6bfa1c6). Live dubai_dishes=0. Owed: loader-valid dubai_uae.json (null 0011 fields + vocabulary) |
| OSM licence position unexamined | Medium | SPEC-19 mines OpenStreetMap and SPEC-20 seeds venues_rag from it, which plausibly makes venues_rag a derivative database under ODbL and attaches share-alike to it if it is ever distributed. Recommendations generated on top are most likely a produced work, needing attribution only. Nobody qualified has looked at either question. Recorded in the SPEC-21 decision record; it needs advice before a city is onboarded from OSM at scale, not after |
| The dietary safety layer has no data source | RESOLVED BY DESCOPING | In OSM, diet:halal covers 20 of 6611 central Bangkok POIs and diet:vegetarian about two percent; Dubai is the best case at six and seven percent. A safety filter with no trustworthy input converts caution into misplaced confidence, so the claim is retired rather than sourced. See the SPEC-14 decision record |
| halal plus pork passes the allergen check | CLOSED BY RETIREMENT | SPEC-14 landed: the app no longer makes any dietary suitability claim. suitable_for is stripped from API responses and never presented or filtered on. The fix is silence, not a rule -- adding LABEL_EXCLUDES_ALLERGENS would have made a wrong answer look considered |
| Most localized names remain unverified | Medium | Forty-eight of 58 stay source=generated. Two known errors are a wrong vowel inside otherwise valid Lao, which no codepoint guard can detect. The driver card's confirm affordance is the mitigation |
| Lao order phrase may say fry, not spicy | Medium | The papaya salad phrase reads bo phat lai, not bo phet lai -- stir-fry rather than spicy, one missing vowel. Needs a native speaker, not a script check. Three of four hot dishes carry no moderating phrase at all, and the raw-meat laap has no cooked-request phrase |
| opening_hours null on all Laos venues | RESOLVED | Device-day reload: 58/58 opening_hours_structured populated |
| hybrid_venue_search geo_region param | Medium | Live signature matches 0001: no geo_region arg. Caller may still pass a filter the RPC ignores -- fix needs a new migration + align |
| price_local units documented, AED rows still suspect | Low | No Dubai venue_dish rows live (count 0). AED magnitude question is moot until dishes are curated |
| Raw-safety guard keys off English prose | Low | The guard that flags an uncooked dish looks for the word raw in the description, so rewording a description silently disables a safety check. Key it off a structured field |
| seniors overcorrected | Low | Set on 40 of 58 venues, roughly two thirds, so it cannot discriminate. mobility_limited is 17 of 58, which is plausible rather than overcorrected -- an earlier version of this table attributed the two-thirds figure to the wrong tag |
| Vientiane has zero massage_spa | Low | Suspect. This was reported by a warning function that was broken until recently, so re-check it against the data rather than trusting the earlier report |
| VALID_DISH_CONTAINS in the wrong file | RESOLVED | Moved into config/dietary.py in PR #15 (d061222). Loader imports the canonical object; identity and set-equality guards in tests/test_valid_dish_contains.py |
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
