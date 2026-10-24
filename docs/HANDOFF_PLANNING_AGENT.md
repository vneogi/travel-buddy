# Planning-agent handoff

Start at `docs/DOCUMENT_MAP.md`. Then read `docs/WAYS_OF_WORKING.md` and
`docs/ENGINEERING_RULES.md`. Those two files are the contract. This file is
only the baton: what is true now, what the previous planning agent already
adjudicated, and what the next agent must not reopen in the first week.

Read this file and the two contracts above. SPEC-36 through SPEC-38,
SPEC-40, SPEC-41 Phase A, G0 field-fix-2, SPEC-45 field trust hygiene,
SPEC-44 Phase A, SPEC-25 grounded, broad, durable trip-scoped Ask,
SPEC-46 What Now Phase A, thin typed Ask-to-Add, thin typed Move,
empty-day catalog Add, trip-private uncatalogued Add, SPEC-43 Gap 1
anonymous JWT, SPEC-43 Gap 6 sign-out, SPEC-43 Gap 2 RLS,
SPEC-43 Gap 9 signal ownership, and SPEC-43 Gap 12 HTTPS fail-closed
are on `main` through `6f1dab8` (PR #82). Hosted 0025 is applied.
Cloud Run `travel-buddy-00012-8wv` is the live untagged revision.
SPEC-42 remains PARTIAL (unknown-time excursions later).
Create-then-book HITL reflow remains. Trip-optional Ask remains.
What Now Phase B GPS remains blocked on remaining SPEC-43. Next is
Gap 12 cache keys (brief not written). Do not apply 0026 until
`rolbypassrls` is confirmed.

SPEC-44 Phase A application code merged as PR #67 (`9a7b9d9`). Planning
reviews; Genie implements. SPEC-43 is the release foundation before any
non-owner tester or the planned December launch. The SPEC-13/17/20 city
factory follows; Bangkok proves it without a hardcoded exception.

## Who does what (unchanged)

- Planning: product, specs, sequencing, review, living docs. No pytest
  claims you did not watch. ASCII in living docs (R14). R17: a guard
  that cannot fail is not a guard.
- Execution (Genie Code): application code, migrations, tests; land via PR.
- Owner: laptop, Flutter on device, live SQL editor, PowerShell. Laptop
  regression runbook: `docs/briefs/LAPTOP_VERIFY.md`. Final phone gate:
  SPEC-37 and `docs/TESTING_GUIDE.md` section 6. Do not invent device results.

## Where we are

The owner Laos field test is complete. The 11 Oct evidence record includes 26
owner observations plus review of 65 Laos and 73 China Gemini turns. The app
worked as an offline itinerary spine; it did not yet provide the broad,
persistent, grounded orchestration the owner used Gemini for. Do not preserve
the pre-departure freeze sequence as current work.

Done on the October spine:

- Device day closed (2026-08-17). Migrations 0011-0018 applied. Live SQL
  sentinels verified 0019-0024 on 2026-09-06, including the 0023
  `filter_geo_region` RPC argument. `docs/HOSTED_STATE.md` is the canonical
  ledger; do not reconstruct migration state from old briefs.
- SPEC-09 client + server. Client: PR #16 (`7173a3f`). Device E2E with
  `TB_ALLOW_ANONYMOUS=true` still owed.
- SPEC-22 October slice. PR #17 (`1b9b1b3`). Envelope widget, five
  treatments, interruption budget, offline state widget,
  PromptDismissAdapter. Font cmap, ARB runtime wiring, screen migration
  deferred.

- SPEC-12 driver card. PR #19 (`a2da64a`). Full-screen offline card on
  `FactView` / `ConfirmAffordance` / `cache_place`, `driver_card_shown` &
  `name_confirmed` signals (migration 0020 verified live 2026-09-06).
- SPEC-10 booking anchors. PR #20 (`f6328e9`). Immovable locked nodes,
  booking metadata on `trip_node` (migration 0021 verified live 2026-09-06),
  on-device regex extractor, `AddBookingSheet`, `booking_added` signal.
- SPEC-04 offline cache floor. PR #22 (`b7e10c3`). Offline itinerary cache
  fallback in `ItineraryController.load()` and pre-cached place data remain.
  The duplicate Hotel Rescue AppBar shortcut was subsequently retired and
  removed.
- Post-spine hardening. PR #23 (`dab16c0`). `geoRegion` threaded from
  `TripNode` to `PlaceDriverCardData` (Lao script & LAK fares resolve live),
  `resetAuthHalted()` on `SyncEngine` + `SyncStatusScreen` `HALTED (401)` card,
  robust hotel matching for villa/guesthouse.

October spine status: ALL 7 CORE ITEMS COMPLETE & HARDENED ON MAIN.

Status tables: `docs/PROJECT_STATUS.md`. Device-only queue:
`docs/AWAITING_VERIFICATION.md`. Hosted schema/provider ledger:
`docs/HOSTED_STATE.md`. Owner-to-store launch ledger:
`docs/RELEASE_READINESS.md`. City sequence:
`docs/MARKET_STRATEGY.md` (Sep 2026 Banana Pancake addendum). The governed
moat and post-Laos data sequence are owned by
`docs/DATA_FLYWHEEL_OPERATING_MODEL.md`; the internal review product is
SPEC-47. P0 trust hygiene, broad persistent SPEC-25 Ask, and SPEC-46 What
Now Phase A (`d1df944`), thin typed Ask-to-Add (`0344b4b`), thin
typed Move (`e51513e`), empty-day catalog Add (`b6ddecf`), and
trip-private uncatalogued Add (`05d917e`) are now on main. SPEC-43 Gap 1
(`2460edf`), Gap 6 (`c65261c`), Gap 2 (`0b8125f`), Gap 9
(`163a14c`), and Gap 12 HTTPS (`6f1dab8`) are on main. The next
Genie job is Gap 12 cache keys after planning writes the brief.
Remaining Gap 9 schema/poisoning, unknown-time excursions, and Laos
decision-cell coverage stay later.
SPEC-43 still gates every non-owner APK. Do not treat in-memory pytest as
PostgreSQL transaction proof.

## Third-party review -- already adjudicated

A full-repo review (Isaac, 2026-08-19) was checked against the tree.
Keep the useful bugs; do not inherit the false ones.

Fixed in PR #18 (`ce8fedb`):

- `replacement_ref` lookup (stable node_id + changed venue).
- Visited/NOW via `nodeIsCurrentWindow` (server still does not stamp ACTIVE).
- Session redirect no longer requires a Supabase session.
- `body2` -> `bodyMedium`.
- Flutter job in `.github/workflows/test.yml` (pytest sibling kept).
- compose Python-as-init.sql mount removed.
- `resetBackoff` keeps `attempts`.
- 401 sets `_authHalted`; connectivity does not clear it.
- Chat empty-state is a question, not a swap.

Still true (do not "fix" by rescoping the field-test gate):

- Offline itinerary reads and pre-cached driver cards are production paths;
  preserve them through all later create, scheduling, and Ask work.
- Chat still sends `ask_info`; broad natural-language mutation remains
  deferred until after the phone gate. When it is built, SPEC-44 Phase D
  and SPEC-25 require typed commands, retrieval-first Ask, HITL persistence,
  and SPEC-29/35 evaluators -- not LangGraph, Temporal, MCP solver tools,
  or a second proactive agent graph.

Reject or defer:

- `firstOrNull` as a compile break -- SDK `>=3.2.0`, method is in
  `dart:core`. Do not add `package:collection` for it.
- "Flutter does not compile" as a two-error headline -- `body2` is the
  confirmed error.
- `1 << 63` overflow to a zero backoff -- Dart VM `int` is arbitrary
  precision; delay is already clamped to 15 minutes.
- "No widget tests" -- SPEC-22 added render widget tests on `1b9b1b3`.
- Hardcoded `POST /trip/create` -- demo fixture, not this month.
- Prompt injection, shared anonymous UUID, and missing rate limits are true.
  They are not owner-only Laos blockers, but are now explicit SPEC-43 release
  blockers before any non-owner distribution.
- Wiring offline itinerary reads by editing the README instead of
  SPEC-12 / thin SPEC-04.
- Deleting `ACTIVE` / `visited_confirmed`.
- Changing swap to mint a new `node_id` (would break SPEC-16).
- Rescoping October toward traction/growth because the survey said
  mid-trip replanning is moderate. The field test is one working trip
  on a phone, not a user-acquisition plan. VISION Part III remains
  not committed. SPEC-24 and SPEC-27 remain unbuilt; several other specs in
  that number range already have partial or completed slices. SPEC-24 and
  SPEC-27 are now dependencies inside SPEC-43 and cannot slip past the first
  non-owner build.

Strategic point that remains true: unique data needs many users per city and
has no owner. SPEC-24 vs accumulating device UUIDs is already a Medium row in
PROJECT_STATUS. It remains required before non-owner distribution, but it does
not outrank the field-proven itinerary trust gaps for the owner's trip.

## Durable post-Laos plan -- do not lose at handoff

The 24 Sep moat review is accepted, not pending advice. Its canonical record is
`docs/DATA_FLYWHEEL_OPERATING_MODEL.md`. It keeps Flutter, Riverpod, SQLite,
FastAPI, Supabase/Postgres, and pgvector; Postgres remains the fact store.
The moat is attributable, fresh, validated evidence about feasible recovery
decisions and later outcomes, not submission count.

Resume in this order:

1. P0 field trust defects are closed on main.
2. Grounded field intents and durable SPEC-25 trip threads are on main.
3. SPEC-46 What Now Phase A is on main (PR #73, `d1df944`): three-to-five
   feasible options, deterministic reasons, named unknowns, and no GPS or
   LLM. Hosted/phone not repeated for this SHA.
4. Thin typed Ask-to-Add (PR #74, `0344b4b`), thin typed Move
   (PR #75, `e51513e`), empty-day catalog Add (PR #76, `b6ddecf`),
   trip-private uncatalogued Add (PR #77, `05d917e`), SPEC-43 Gap 1
   anonymous JWT (PR #78, `2460edf`), and SPEC-43 Gap 6 sign-out
   (PR #79, `c65261c`), SPEC-43 Gap 2 RLS (PR #80, `0b8125f`),
   SPEC-43 Gap 9 ownership (PR #81, `163a14c`), and SPEC-43 Gap 12
   HTTPS (PR #82, `6f1dab8`) are on main. Unknown-time excursion
   windows stay later. Never silently reflow a day.
5. Patch Laos spine and effective-choice gaps: Kuang Si, Pak Ou, Blue Lagoon
   2/3, Papao, and the Wat Xieng Thong packing failure. Measure coverage by
   common decision cell, not total POI count.
6. Implement remaining SPEC-43 (next: Gap 12 cache keys) before any
   non-owner APK, hostel QR, production LLM on personal trips, or
   contribution collection. Hosted 0026 waits on `rolbypassrls`.
7. Implement SPEC-13 identity plus the minimum SPEC-17 claim/attribute
   registry, append-only observation lifecycle, and SPEC-44 decision capture.
   Keep learned influence at zero.
8. Build the minimum protected SPEC-47 review queue before contribution
   prompts turn on.
9. Run one narrow, consented Laos-corridor evidence pilot. Measure
   corroboration, disputes, correction time, review cost, withdrawal/deletion,
   and accept-to-visit/outcome -- not raw submissions.
10. Implement SPEC-20 versioned city/route packs. Bangkok proves the factory;
   Chiang Mai and Pai follow only after that proof.
11. Permit learned ranking influence only after held-out evidence, sample-size
   gates, inspectability, rollback, consent, and deletion are demonstrated.

Travelogue/Passport, maps/offline tiles, social, gamification, PDF, cross-trip
memory, OTA promotion, another city, microservices, a graph database, and
another vector database are deferred. The detailed gates and data-plane
separation live in the operating model; do not reconstruct them from chat.

## First job

`origin/main` includes SPEC-43 Gap 12 HTTPS as `6f1dab8` (PR #82).
Hosted 0025 applied. Cloud Run `00012-8wv`. Owner APK SHA256
`bd935bf2...`.

Genie next: wait for the Gap 12 cache-key brief. Do not implement
cache keys, remaining Gap 9 schema/poisoning, Gap 5, production LLM,
trip-less Ask, or unknown-time excursions without that brief. Do not
apply 0026 until `rolbypassrls` is confirmed for `postgres` and
`service_role`. Do not deploy Gap 1/6 until Anonymous sign-ins and
JWKS env are set. Do not merge, deploy, or build an APK from this
docs update.

Historical context (do not treat as current work):

- SPEC-40 is done as `ebdea52`. SPEC-42 uncap is PARTIAL on main
   (`17e58ac`): catalog caps are gone and empty dates render. Do not
   reopen the five-day *starter* budget. Empty-day catalog Add (`b6ddecf`)
   and trip-private uncatalogued Add (`05d917e`) are on main.
- SPEC-41 Phase A is complete. A3a merged as `d1fde14`; A3b branch head
   `7f25042` replaces the 30-minute buffer and random/clock mock transit with
   deterministic walking time, city/day boundaries, apply-time retry,
   previous-node reachability, and next locked-anchor constraints.
- SPEC-10 provider-aware paste is on main (`fc6926b`). Flight/hotel
   scheduler remainder is on main (`e7a0457`). Do not reopen Agoda adapters
   unless a new redacted fixture fails. Keep SPEC-10 PARTIAL until
   create-then-book HITL reflow exists.
- SPEC-25 trip-scoped grounded Ask is on main (`30a4270`). Laptop Flutter
   Ask envelope tests passed. Owner Windows `pytest -q` on `3e5ec6d` is
   green (details in AWAITING_VERIFICATION). Trip-optional Ask remains.
- Hotel wall-time conversion, weather empty-key, and swap canned copy
   after `no_candidates` are on main (`933c705`).
- Specified remainders are sequenced in
   `docs/briefs/GENIE_REMAINDERS_SEQUENCE.md`. Slice 1 (uncap) is on
   main (`17e58ac`). Slice 2 (hotel stay display) is on main
   (`1f251a3`, merge `7b62818`). Slice 3 (named slots) is on main
   (`f1feb17`, merge `9173b23`). G0 field-fix-2 is on main (`b8cf305`).
   SPEC-45 Phase A is on main (`7939565`). Create-then-book HITL
   reflow remains. Do not start inspiration, similar-trip generation,
   or broader consumer work during the departure freeze.
- SPEC-44 Phase A is closed on main (`9a7b9d9`). Hosted 0025 is
   applied. Remainders A4/A5 and Flutter command queue wait until after
   the Laos trip unless a blocker requires them.
- Implement SPEC-43 in bounded phases. It owns twelve verified gaps:
   server-issued anonymous auth, complete RLS, redacted LLM egress, data rights
   and retention, encrypted offline data, real sign-out, purpose consent,
   private cache isolation, signal ownership/poisoning controls, redacted
   diagnostics, abuse/spend limits, and release HTTPS/cache isolation.
- Do not distribute an APK to another person, enable production LLM processing
   of personal trip data, or claim residency/compliance before SPEC-43's
   applicable gates pass.
- After SPEC-43, implement the SPEC-13 region/country registry, minimum
   SPEC-17 claim/attribute registry and append-only observation lifecycle.
   Add SPEC-44 recommendation-decision capture only for consented subjects.
    Record feasible exposure, exclusions, score components, displayed order,
    sponsorship, and policy/catalog/taxonomy versions. Learned influence stays
    zero until held-out evidence and rollback gates pass.
- Build the minimum SPEC-47 protected review queue before contribution
   prompts turn on. Run the narrow Laos evidence pilot before SPEC-20 expands
   the versioned pack model. Bangkok is the city-factory acceptance case; do
   not add Thailand, Vietnam, Cambodia, or Philippines through another
   Python/Dart/loader exception.
- Only after SPEC-44 Phase A and the matching online SPEC-42 action exist,
    consider SPEC-02's separate SQLite mutation-command outbox. Queue typed
    confirmed commands with `command_id` and `expected_version`; never perform
    local reflow or silently resolve a conflict.
- Only after Bangkok proves the SPEC-20 city factory, prototype SPEC-04's
    optional versioned offline map artifact on representative devices. PMTiles,
    MapLibre, and Cloudflare R2 are candidates, not commitments; measured size,
    cold start, rendering, memory, battery, update, and offline behavior decide.

Migrations through 0025 and the Maps/OpenWeather local provider credentials are
already verified; do not ask for them again unless a new migration or
credential rotation occurs. See `docs/HOSTED_STATE.md`. Local provider success
does not establish hosted deployment configuration.

Do not start with another full-repo archaeology. The defects that matter on
itinerary are listed above. The future-readiness decisions and explicit
deferrals are in `docs/specs/SPEC-44-backend-future-readiness.md`. If a new
claim needs checking, verify that claim; do not re-read every migration.

## Review habits that already failed here

- Read the diff, not the agent's summary.
- R17 sabotage: break the production predicate, name the test that
  went red, restore.
- Never quote pytest counts into living docs (R16).
- Never state Flutter or live SQL results you did not watch.
- After merge, read `origin/main`, not the working copy.
- At handoff or likely context compaction, run the continuity checkpoint in
  `docs/WAYS_OF_WORKING.md`: start from `DOCUMENT_MAP.md`, route decisions,
  update Now / Next / Later, commit and push docs, and state whether they
  reached `main`.

## What not to "simplify"

The markdown-to-Python ratio is high on purpose. Specs 18-27 are the
corridor after October. Cutting them in week one to look lean is how
the project forgets why SPEC-12 is shaped as it is.

`ENGINEERING_RULES.md` R1-R17 each name a commit. Do not collapse them
into a style guide.
