# Planning-agent handoff

Read this after `docs/WAYS_OF_WORKING.md` and `docs/ENGINEERING_RULES.md`.
Those two files are the contract. This file is only the baton: what is true
now, what the previous planning agent already adjudicated, and what the
next agent must not reopen in the first week.

Switch is valid only after all three:

1. This docs commit is on `main` (SPEC-22 status pointers + this file).
2. The PR from `docs/briefs/GENIE_ITINERARY_SIGNAL_FIXES.md` is merged.
3. You have read this file and the two contracts above.

Until (2) lands, the execution agent is still on that brief, not SPEC-12.

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

Next after the fix PR: SPEC-12 driver card on `FactView` /
`ConfirmAffordance` / `cache_place`. Then SPEC-10, then thin SPEC-04
hotel rescue. That order is the spine. Do not reverse it.

Status tables: `docs/PROJECT_STATUS.md`. Device-only queue:
`docs/AWAITING_VERIFICATION.md`.

## Third-party review -- already adjudicated

A full-repo review (Isaac, 2026-08-19) was checked against the tree.
Keep the useful bugs; do not inherit the false ones.

Keep (most are the Genie brief above):

- `replacement_ref` lookup inverted while swap preserves `node_id`.
- `NodeStatus.active` never assigned; `visited_confirmed` unreachable.
- Chat placeholder promises a swap; chat always sends `ask_info`.
- Session redirect vs skip-onboarding loop; worse after SPEC-09.
- `AppTypography.body2` in `profile_screen.dart`.
- `cacheTrip` / `getCachedTrip` have no production callers (reads).
- `docker-compose` mounts Python as `init.sql`.
- No Flutter job in CI.
- 401 "halt" is a comment; 60s timer still runs.
- `resetBackoff` zeroes `attempts` on every reconnect.

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

## First job after the fix PR

Write and review the SPEC-12 Genie brief. Use `FactView`,
`ConfirmAffordance`, and SPEC-02 `cache_place`. One migration for
`name_confirmed` and `driver_card_shown` if the spec still says that.

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
