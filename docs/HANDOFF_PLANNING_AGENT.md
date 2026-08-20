# Planning-agent handoff

Read this after `docs/WAYS_OF_WORKING.md` and `docs/ENGINEERING_RULES.md`.
Those two files are the contract. This file is only the baton: what is true
now, what the previous planning agent already adjudicated, and what the
next agent must not reopen in the first week.

Switch is valid: PR #18 is on `main` (`ce8fedb`). Read this file and
the two contracts above. First execution brief to write: SPEC-12.

## Who does what (unchanged)

- Planning: product, specs, sequencing, review, living docs. No pytest
  claims you did not watch. ASCII in living docs (R14). R17: a guard
  that cannot fail is not a guard.
- Execution (Genie Code): application code, migrations, tests; land via PR.
- Owner: laptop, Flutter on device, live SQL editor, PowerShell. Runbook:
  `docs/briefs/LAPTOP_VERIFY.md`. Do not invent device results.

## Where we are

Forcing function: Laos field test, 2 October.

Done on the October spine:

- Device day closed (2026-08-17). Migrations 0011-0018 applied. 0019
  (`prompt_dismissed`) is in the repo, unapplied live.
- SPEC-09 client + server. Client: PR #16 (`7173a3f`). Device E2E with
  `TB_ALLOW_ANONYMOUS=true` still owed.
- SPEC-22 October slice. PR #17 (`1b9b1b3`). Envelope widget, five
  treatments, interruption budget, offline state widget,
  PromptDismissAdapter. Font cmap, ARB runtime wiring, screen migration
  deferred.

- SPEC-12 driver card. PR #19 (`a2da64a`). Full-screen offline card on
  `FactView` / `ConfirmAffordance` / `cache_place`, `driver_card_shown` &
  `name_confirmed` signals (migration 0020 in repo, unapplied live).
- SPEC-10 booking anchors. PR #20 (`f6328e9`). Immovable locked nodes,
  booking metadata on `trip_node` (migration 0021 in repo, unapplied live),
  on-device regex extractor, `AddBookingSheet`, `booking_added` signal.
- SPEC-04 hotel rescue & offline cache. PR #22 (`b7e10c3`). <=2-tap hotel
  rescue entry to `DriverCardScreen`, offline itinerary cache fallback in
  `ItineraryController.load()`, pre-caching hotel place data.
- Post-spine hardening. PR #23 (`dab16c0`). `geoRegion` threaded from
  `TripNode` to `PlaceDriverCardData` (Lao script & LAK fares resolve live),
  `resetAuthHalted()` on `SyncEngine` + `SyncStatusScreen` `HALTED (401)` card,
  robust hotel matching for villa/guesthouse.

October spine status: ALL 7 CORE ITEMS COMPLETE & HARDENED ON MAIN.

Status tables: `docs/PROJECT_STATUS.md`. Device-only queue:
`docs/AWAITING_VERIFICATION.md`.

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

Still true (do not "fix" by rescoping October):

- `cacheTrip` / `getCachedTrip` have no production callers (reads).
  Wire on SPEC-12 / thin SPEC-04, not a README edit.
- Chat still always sends `ask_info`; do not build NL swap this week.

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
  not committed. SPEC-18 through SPEC-27 stay specified and unbuilt.

Strategic point that is true and still not a spine change: unique data
needs many users per city and has no owner. Date a note after the field
test. Do not steal SPEC-12's week for it. SPEC-24 vs accumulating
device UUIDs is already a Medium row in PROJECT_STATUS; date it, do not
implement merge before the driver card.

## First job

All 7 items on the October field-test spine are complete on main.
Next tasks:
1. Owner laptop verification run (docs/briefs/LAPTOP_VERIFY.md) for 0019-0021
   live apply, Anonymous E2E, and Chrome smoke.
2. observed_duration_minutes writer (SPEC-16 gap).
3. Post-October consumer surface specs (SPEC-26, SPEC-25, SPEC-27).

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
