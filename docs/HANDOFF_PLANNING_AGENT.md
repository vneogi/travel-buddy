# Planning-agent handoff

Read this after `docs/WAYS_OF_WORKING.md` and `docs/ENGINEERING_RULES.md`.
Those two files are the contract. This file is only the baton: what is true
now, what the previous planning agent already adjudicated, and what the
next agent must not reopen in the first week.

Read this file and the two contracts above. SPEC-36 through SPEC-38 and
SPEC-40 are done. SPEC-41 Phase A2 merged as `377125e`. The first job is A3a
window-aware packing and truthful capacity, followed by A3b deterministic
transit and locked-anchor reachability. Then come SPEC-10 provider-aware paste
and SPEC-25 grounded trip-scoped Ask.

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
  deferred until after the phone gate.

Reject or defer:

- `firstOrNull` as a compile break -- SDK `>=3.2.0`, method is in
  `dart:core`. Do not add `package:collection` for it.
- "Flutter does not compile" as a two-error headline -- `body2` is the
  confirmed error.
- `1 << 63` overflow to a zero backoff -- Dart VM `int` is arbitrary
  precision; delay is already clamped to 15 minutes.
- "No widget tests" -- SPEC-22 added render widget tests on `1b9b1b3`.
- Hardcoded `POST /trip/create` -- demo fixture, not this month.
- Prompt injection, shared anonymous UUID, missing rate limit -- true,
  not October-blocking.
- Wiring offline itinerary reads by editing the README instead of
  SPEC-12 / thin SPEC-04.
- Deleting `ACTIVE` / `visited_confirmed`.
- Changing swap to mint a new `node_id` (would break SPEC-16).
- Rescoping October toward traction/growth because the survey said
  mid-trip replanning is moderate. The field test is one working trip
  on a phone, not a user-acquisition plan. VISION Part III remains
  not committed. SPEC-24 and SPEC-27 remain unbuilt; several other specs in
  that number range already have partial or completed slices.

Strategic point that remains true: unique data needs many users per city and
has no owner. SPEC-24 vs accumulating device UUIDs is already a Medium row in
PROJECT_STATUS. It remains required before non-owner distribution, but it does
not outrank the field-proven itinerary trust gaps for the owner's trip.

## First job

The phone-independent delivery and airplane-mode gate passed. SPEC-38 passed
on the owner's phone. Next tasks:

1. SPEC-40 is done as `ebdea52`; do not reopen its current five-day foundation
   while implementing later sparse-span work.
2. SPEC-41 Phase A2 is merged as `377125e`. Next is A3a:
   `docs/briefs/GENIE_SPEC_41_PHASE_A3A_WINDOW_PACKING.md`. It schedules
   venues into later same-day windows and removes the three-region
   identity-capacity mismatch. A3b then adds deterministic transit and
   locked-anchor reachability.
3. Implement the SPEC-10 provider-aware paste remainder with redacted Agoda and
   Booking.com fixtures and honest partial extraction.
4. Implement the SPEC-25 grounded trip-scoped Ask remainder. Key presence alone
   is not acceptance; retrieval and named fallback states are required.
5. Re-run hosted API, signed APK, and device acceptance for those slices before
   inspiration, similar-trip generation, or broader consumer work.

Migrations through 0024 and the Maps/OpenWeather local provider credentials are
already verified; do not ask for them again unless a new migration or
credential rotation occurs. See `docs/HOSTED_STATE.md`. Local provider success
does not establish hosted deployment configuration.

Do not start with another full-repo archaeology. The defects that
matter on itinerary are listed above. If a new claim needs checking,
verify that claim; do not re-read every migration.

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
