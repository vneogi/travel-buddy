# Planning-agent handoff

Read this after `docs/WAYS_OF_WORKING.md` and `docs/ENGINEERING_RULES.md`.
Those two files are the contract. This file is only the baton: what is true
now, what the previous planning agent already adjudicated, and what the
next agent must not reopen in the first week.

Read this file and the two contracts above. SPEC-36 through SPEC-38 and
SPEC-40 are done. SPEC-41 Phase A is complete: A3a merged as `d1fde14` and
A3b was reviewed at branch head `7f25042`. SPEC-10 paste is on main
(`fc6926b`). Flight/hotel scheduler remainder is on main (`e7a0457`);
destination-local booking times, weather empty-key, and swap canned copy
after honest refusal are on main (`933c705`). `pack_day` booking
constraints stay deferred. SPEC-25 trip-scoped grounded Ask is on main
(`30a4270`); trip-optional Ask remains. After hosted/API/APK verification, SPEC-44
Phase A makes trip persistence transactional. SPEC-43 is then the release
foundation before any non-owner tester or the planned December launch. The
SPEC-13/17/20 city factory follows; Bangkok proves it without a hardcoded
exception.

## Who does what (unchanged)

- Planning: product, specs, sequencing, review, living docs. No pytest
  claims you did not watch. ASCII in living docs (R14). R17: a guard
  that cannot fail is not a guard.
- Execution (Genie Code): application code, migrations, tests; land via PR.
- Owner: laptop, Flutter on device, live SQL editor, PowerShell. Laptop
  regression runbook: `docs/briefs/LAPTOP_VERIFY.md`. Final phone gate:
  SPEC-37 and `docs/TESTING_GUIDE.md` section 6. Do not invent device results.

## Where we are

Forcing function: Laos field test, 2 October.

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
`docs/HOSTED_STATE.md`. Next implementation contract:
`docs/specs/SPEC-41-hours-aware-scheduling.md`.

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

## First job

The phone-independent delivery and airplane-mode gate passed. SPEC-38 passed
on the owner's phone. Next tasks:

1. SPEC-40 is done as `ebdea52`; do not reopen its current five-day foundation
   while implementing later sparse-span work.
2. SPEC-41 Phase A is complete. A3a merged as `d1fde14`; A3b branch head
   `7f25042` replaces the 30-minute buffer and random/clock mock transit with
   deterministic walking time, city/day boundaries, apply-time retry,
   previous-node reachability, and next locked-anchor constraints.
3. SPEC-10 provider-aware paste is on main (`fc6926b`). Flight/hotel
   scheduler remainder is on main (`e7a0457`). Do not reopen Agoda adapters
   unless a new redacted fixture fails. Keep SPEC-10 PARTIAL until
   `pack_day` takes bookings.
4. SPEC-25 trip-scoped grounded Ask is on main (`30a4270`). Laptop Flutter
   Ask envelope tests passed (18). Owner `pytest -q` on `a586e78` was
   755 passed / 4 failed; those four are the env-guard cases already on
   main as `933c705`. Trip-optional Ask, model phrasing/budget/breaker UX
   remain. Key presence is not acceptance.
5. Hotel wall-time conversion, weather empty-key, and swap canned copy
   after `no_candidates` are on main (`933c705`). Catalog date caps, named
   slots, hotel coords, and dual check-in/out stay specified.
6. Next owner gate: `pytest -q` on current main (expect those four green),
   then hosted API, signed APK, and device Ask. After that, do not start
   security implementation, inspiration, similar-trip generation, or
   broader consumer work until the phone gate.
7. Implement SPEC-44 Phase A. Make trip graph, party, compatibility projection,
   and command record one transaction; add monotonic trip version,
   `expected_version`, typed conflict, idempotent command IDs, and production
   PostgreSQL contract tests. Do this before SPEC-16 row-authoritative reads,
   multi-device mutation, or a second real city.
8. Implement SPEC-43 in bounded phases. It owns twelve verified gaps:
   server-issued anonymous auth, complete RLS, redacted LLM egress, data rights
   and retention, encrypted offline data, real sign-out, purpose consent,
   private cache isolation, signal ownership/poisoning controls, redacted
   diagnostics, abuse/spend limits, and release HTTPS/cache isolation.
9. Do not distribute an APK to another person, enable production LLM processing
   of personal trip data, or claim residency/compliance before SPEC-43's
   applicable gates pass.
10. After SPEC-43, implement the SPEC-13 region/country registry, minimum
   SPEC-17 claim store, and SPEC-20 versioned city pack. Bangkok is the
   acceptance case. Do not add Thailand, Vietnam, Cambodia, or Philippines data
   through another Python/Dart/loader exception.
11. Add SPEC-44 recommendation-decision capture only for consented subjects.
    Record feasible exposure, exclusions, score components, displayed order,
    sponsorship, and policy/catalog/taxonomy versions. Learned influence stays
    zero until held-out evidence and rollback gates pass.
12. Only after SPEC-44 Phase A and the matching online SPEC-42 action exist,
    consider SPEC-02's separate SQLite mutation-command outbox. Queue typed
    confirmed commands with `command_id` and `expected_version`; never perform
    local reflow or silently resolve a conflict.
13. Only after Bangkok proves the SPEC-20 city factory, prototype SPEC-04's
    optional versioned offline map artifact on representative devices. PMTiles,
    MapLibre, and Cloudflare R2 are candidates, not commitments; measured size,
    cold start, rendering, memory, battery, update, and offline behavior decide.

Migrations through 0024 and the Maps/OpenWeather local provider credentials are
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

## What not to "simplify"

The markdown-to-Python ratio is high on purpose. Specs 18-27 are the
corridor after October. Cutting them in week one to look lean is how
the project forgets why SPEC-12 is shaped as it is.

`ENGINEERING_RULES.md` R1-R17 each name a commit. Do not collapse them
into a style guide.
