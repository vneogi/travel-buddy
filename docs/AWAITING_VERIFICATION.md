# Awaiting Verification

Consolidated Aug 14 2026. This file is a dated log of what cannot be verified
from a keyboard, plus the findings that were retracted and the tooling
incidents worth not repeating. It is the only place in the repo where dated
observations belong (R16).

What it deliberately does not carry: the device-day task order, which lives in
`docs/PROJECT_STATUS.md` with the runnable Windows PowerShell steps in
`docs/briefs/DEVICE_DAY.md`. Two documents holding the same ordered list is how
they end up contradicting each other, which is what this consolidation is
fixing.

Commits are identified by SHA only. Earlier revisions numbered work as `#84`,
`#85` and so on; those numbers cannot be reconciled against `git log`.

## What cannot be verified without a device or credentials

| Area | Unverified since | Verify with |
|---|---|---|
| Migrations 0011 to 0018 | applied device day 2026-08-17 | VALIDATE on NOT VALID CHECKs still deferred; confirm via Step 7 |
| The five Supabase tests | ran green 2026-08-17 | `280 passed` suite with TB_SUPABASE_URL; see finding below |
| Flutter client follow-ups | Aug 30 2026 Windows run | Windows desktop or Android. Chrome is layout-only while web SQLite remains experimental. Profile/Skip exact errors remain open; durable hearts passed Aug 30 |
| Migration 0019 prompt_dismissed | landed `1b9b1b3`, unapplied | LAPTOP_VERIFY Step 3; then signal_types tests |
| Migration 0020 driver_card_signals | landed `a2da64a`, unapplied | Apply via Supabase SQL editor; then signal_types drift tests |
| Migration 0021 booking_anchors | landed `f6328e9`, unapplied | Apply via Supabase SQL editor; then signal_types drift tests |
| Migration 0022 trip_node_local_names | landed, unapplied | Apply via Supabase SQL editor; adds names_local, landmarks_local, nearest_landmark to trip_node |
| Migration 0023 driver_card_search_fields | in repo, unapplied | Apply via Supabase SQL editor; updates hybrid_venue_search to return geo/localized driver-card fields and accept filter_geo_region |
| Migration 0024 session_start | applied hosted Aug 30-31 (owner SQL editor) | Required before live ingest accepts the type. After apply: session_start accepted=1 |
| PowerShell scripts | Aug 9 | `.\scripts\smoke-test.ps1` on Windows |
| Laptop-feedback product gaps | Sep 4 2026 | Multi-night hotel UI, hotel rescue selection (6C not run), Windows Maps hand-off, real location, and device-verify of SPEC-32 Laos create remain open. Date grouping and booking edit/delete/notes passed Sep 4. Durable hearts closed Aug 30 |
| `hybrid_venue_search` geo_region parameter | Observed Aug 17 2026 | Live signature matches 0001: no geo_region arg (radius-only). Multi-city RPC filter still absent |
| Dubai row contents, including AED magnitudes | Cleared Aug 17 2026 | 16 Dubai venues live (null price_band). dubai_dishes=0 -- nothing to inspect for AED; food data is greenfield |
| `pg_description` non-ASCII | Cleared Aug 17 2026 | Step 7c returned 0 rows |

The five Supabase integration tests ran green on device day 2026-08-17 with
`TB_SUPABASE_URL` set (`280 passed` suite). Remaining credential-gated gaps
are smoke-test.ps1, any unrecorded Anonymous E2E, and deliberate VALIDATE of
NOT VALID CHECKs.

## Finding -- Sep 4 2026 -- Owner laptop verification (Windows)

Recorded against `main` after PR #37 (`364d873`). Anonymous create/list needed
`TB_ALLOW_ANONYMOUS=true` with JWT unset; without it `/trips` returned 401.

Hosted schema: signal types include `prompt_dismissed`, `driver_card_shown`,
`name_confirmed`, `booking_added`, and `session_start`. Booking and local-name
columns are present. `hybrid_venue_search` already has `filter_geo_region`
(0023). Re-running 0023 is a no-op / duplicate-function error.

Product smoke:

- 6A date grouping passed: 5 Oct present, 6 Oct added, headers looked correct.
- 6B booking notes, edit, and delete passed. Sync reported accepted events and
  no rejection.
- 6C hotel rescue was not run. The booking date picker is one day, which matches
  `scheduled_start` plus duration. Multi-night check-in/out remains unbuilt.

Owner later called the hotel-rescue AppBar shortcut useless. Treat that as an
open product cut, not a 6C result. Profile overflow (`profile_screen.dart`) and
an earlier ErrorView overflow after 401 are separate layout findings.

SPEC-32 catalog-backed create is implemented in this branch. A Windows create
of a Laos city is still unverified.

## Finding -- Aug 31 2026 -- SPEC-30 on origin/main

PR #32 squash-merged as `f8349a8`. CI lint, pytest, Flutter analyze, and Flutter
test were green on that SHA. Deploy/build skipped on the PR (expected).

Do not merge `feat/session-start-signal` or `feat/observed-duration-writer`.
PR #30 and PR #31 were closed without merge because their contents were already
in #32.

Laptop (Windows, against the integration branch then main):

- Pytest for session_start, observed_duration, backend_parity, and signal_types
  passed. Local ruff was not installed; CI Ruff 0.16.3 is the format authority.
- First `session_start` ingest was `rejected=1` until hosted `signal_type`
  included the new row. After migration 0024 in the SQL editor: `accepted=1
  rejected=0`.
- Alerts `GET /trip/{id}/alerts` 503 is missing OpenWeather key, unrelated.
- `flutter test test/session_start_test.dart`: mock `NetworkException` and call
  `syncEngine.stop()` before `db.close()`.

PR #34 completed the traveller-facing remainder as `83c825f`: durable
identity/trip/node-scoped outcomes, active/past "did this happen", outcome-aware
targeting, explicit cancel confirmation, and a scrollable skip-reason sheet.
Owner Windows full Flutter suite: 176 passed. CI lint, pytest, backend test, and
Flutter all green.

Product remainder (not a merge defect): date grouping, date-aware hotel rescue,
booking edit/delete, and multi-night hotel UI.

## Finding -- Aug 30 2026 -- Owner laptop verification (Windows, second laptop)

Recorded against `fix/mobile-missing-imports` (`main` at `acad4b9` plus two
restored imports). Backend on `127.0.0.1:8000`, `supabase_configured=True`.

Build blocker, fixed:

- `main` did not compile for Windows desktop. `itinerary_screen.dart` referenced
  `signalServiceProvider` with no `core/providers.dart` import -- the import was
  dropped in the SPEC-29 unused-import cleanup, where it was not unused -- and
  `chat_screen.dart` referenced `nextMovableStop` with no `current_window.dart`
  import. Five analyzer errors, desktop build failed. Fixed in PR #31 contents
  (landed via PR #32). `flutter test` never caught it because the suite does not
  compile the screen widgets, and `flutter analyze` was already red for an
  unrelated reason, so the errors went unread.

Passed:

- Durable hearts survived a full app close and a fresh `flutter run`. The
  SPEC-02 hearts slice works on device.

Open product gaps observed (known near-term gates, not regressions):

- No day separation. A Mad Monkey booking dated in October shows inside the
  single "Your Day" list with no per-day grouping.
- Booking nodes cannot be reopened, edited or deleted once created;
  AddBookingSheet only creates. SPEC-10 remainder.
- No multi-day hotel entry. AddBookingSheet models a booking as one
  `scheduled_start` plus a duration (hotel defaults to 8h). The scheduler
  background-anchor fix is correct for a single anchor node; `trip_stay`
  check-in/check-out (VISION section 18) is Part III and unbuilt.
- "Cancel next stop" target confirmation was absent in this run. Closed by
  SPEC-30 PR #34 (`83c825f`).

Config note:

- `GET /trip/{id}/alerts` returned 503 (`weather_provider_unavailable`) when
  `OPENWEATHER_API_KEY` was unset. Client maps 503 to
  `WeatherUnavailableException` and falls back to cache.

## Finding -- Aug 27-28 2026 -- Owner laptop verification (Windows)

Recorded against `main`; SPEC-29 subsequently landed as `aedbc03` in PR #25.

Passed:

- A trip survived app kill and uvicorn restart with the same trip id and card
  when startup reported `supabase_configured=True`.
- The Mad Monkey Booking.com paste produced hotel type, `Mad Monkey Vang
  Vieng`, the expected dates and a locked booking.
- The Dubai driver card behaved honestly in airplane mode: no fare claim and
  no screenshot-for-offline instruction.
- Backend-down states used cached content where available and human copy rather
  than Dart, Dio or SQLite internals.

Addressed after the run by SPEC-29:

- Heads-up alerts now use OpenWeather evidence. Synthetic transit estimates,
  including random traffic and "unreachable" copy, cannot be presented as
  traveller facts.
- Cancel is a deterministic skip that preserves the node's position; it no
  longer looks like a swap. Locked cancellation is refused before quota use.

Open product gaps:

- Hotel rescue selects the first hotel-like node instead of the current or next
  date-appropriate stay.
- Bookings have no edit/delete flow, notes are absent from cards, and the
  itinerary has no date grouping.
- Create-trip still seeds the Dubai template; it cannot create a real Laos trip
  (superseded in code by SPEC-32 on this branch; device-verify a Laos city).
- `geo:` Maps hand-off fails on Windows. Keep coordinates available until a
  platform-specific hand-off exists.
- Hearts live in the auto-disposed itinerary controller and are not durable.
  Sync Status starts `syncOnce()` without awaiting it before reading counts.
- Near-me uses default Dubai coordinates rather than device location, and chat
  recommendations have no add-to-trip control.
- Exact Profile and Skip error strings remain unknown.

Windows AXTree console spam was Flutter engine noise; the app continued to run.
Chrome remains useful for layout, but Windows desktop or Android is the field
verification target.

## Open issues that need a person, not a test

### High -- the Dubai venues have no loader-valid source file

Durability landed as `data/dubai_uae_raw_snapshot.json` (`6bfa1c6`,
`not_loader_source: true`, 16 venues). Live `venue_dish` count for Dubai is
**0**. Still owed: curated `data/dubai_uae.json` that passes
`load_venues.py --dry-run` (fill null 0011 fields; map Dubai categories /
audiences / vibes into loader vocabulary; optionally add dishes). Do not pass
the raw dump to the loader.

### Medium -- two Lao vowel errors that no guard can catch

Script-range tests catch Chinese or Thai characters sitting in a Lao field.
They cannot catch a wrong vowel inside otherwise correct Lao. Two are known:
one in a Wat Mai name, and a suspected one in the `tam_mak_hoong` order phrase,
which reads as "do not fry much" where "not too spicy" is intended -- a missing
leading vowel. Both need a native reader. This is the reason the driver card
asks the traveller to confirm rather than asserting.

### Medium -- spice and raw-meat phrasing is incomplete

Four dishes are marked hot and only one carries a spice modifier phrase.
`laap_dib` is raw meat with no "cooked please" phrase at all. Related: the
raw-safety guard keys off the English word "raw" appearing in description
prose, so a reword silently disables it, and the spice keywords are spelled
with PHAT where PHET is meant. The keyword spelling must be corrected together
with the data, never separately, or the search stops matching today's text.


## Finding -- Aug 17 2026 -- Device Day closed

Full Windows device day completed. Durable outcomes:

- Dubai durability: `data/dubai_uae_raw_snapshot.json` at `6bfa1c6`
  (`not_loader_source`, 16 venues). Loader-valid `dubai_uae.json` still owed.
- 0011 dual-column gate: OpenAPI 22 columns; neither `name_local` nor
  `names_local`; applied 0011-0018 via Supabase SQL editor.
- Laos reload: 58 venues + 30 glossary; hours 58/58 structured.
- Pytest: `280 passed` with live `TB_SUPABASE_URL` (five Supabase tests included).
- price_band: dish vocab clean; venues_rag non-null matches 0017; 16 nulls =
  Dubai. VALIDATE deferred.
- Dubai `venue_dish` count live: **0** (confirms raw dump; no AED magnitudes
  to inspect). Food curation for Dubai is greenfield.
- pg_description non-ASCII: 0 rows.
- `hybrid_venue_search` live args = migration 0001 (no geo_region).

October spine: all 7 items complete on main (Device Day, SPEC-09 client,
SPEC-22, fixes PR #18, SPEC-12 `a2da64a`, SPEC-10 `f6328e9`, and SPEC-04
`b7e10c3`). Hardening landed in PR #23 (`dab16c0`). Owner laptop runbook:
docs/briefs/LAPTOP_VERIFY.md (0019, 0020, 0021, Anonymous E2E, sabotage,
Windows/Android). Planning-agent handoff: docs/HANDOFF_PLANNING_AGENT.md.

## Finding -- Aug 20 2026 -- PR #23 Post-Spine Hardening

PR #23 squash-merged as `dab16c0`. All CI checks passed (pytest 287 passed,
ruff clean, flutter analyze 0 errors/0 warnings, flutter test 92 passed):
- `geoRegion` threaded from `TripNode` to `PlaceDriverCardData.fromTripNode`
  so native script resolves. The later laptop run correctly showed no fare.
- `resetAuthHalted()` on `SyncEngine` + `SyncStatusScreen` `HALTED (401)` status
  card.
- `findHotelNode` matches villa/guesthouse accommodation.
- Safe `as Map?.cast<String, dynamic>()` on `PlaceDriverCardData.fromJson`.

## Finding -- Aug 20 2026 -- PR #22 Flutter on CI

PR #22 squash-merged as `b7e10c3`. All CI checks passed: `flutter analyze
--no-fatal-infos` (0 errors, 0 warnings), `flutter test` (all tests passed),
backend `pytest` (287 passed), and `ruff` lint+format clean. Remaining
laptop work is 0019, 0020, 0021 apply and Anonymous E2E.

## Finding -- Aug 20 2026 -- PR #20 Flutter on Windows

SHA `523c6f3` (then squash-merged as `f6328e9`). Owner ran from `mobile/`:
`flutter test`: all 83 tests passed. Backend pytest: 287 passed, signal
drift guard green. Remaining laptop work is 0019, 0020, 0021 apply and
Anonymous E2E.

## Finding -- Aug 17 2026 -- Steps 5d + 7 live SQL (partial)

**5d opening hours:** all Laos venues have `opening_hours_structured` --
luang_prabang 23/23, vang_vieng 15/15, vientiane 20/20.

**7a price_band:**
- `venue_dish`: budget 28, mid 13, splurge 3 (no nulls; no `free`/`premium`).
- `venues_rag`: budget 35, free 5, mid 15, splurge 3, **null 16**.
  Non-null set matches 0017 CHECK (`budget`/`free`/`mid`/`splurge`). The 16
  nulls are the Dubai rows (known from raw dump). Do not VALIDATE today unless
  deliberately accepting NULL-as-allowed; CHECK already permits NULL.

**7b Dubai dishes:** `dubai_dishes = 0`. No AED magnitudes to observe. Raw
dump's `venue_dishes: 0` confirmed live.

Corrected 7b (already run):

```sql
SELECT count(*) AS dubai_dishes
FROM venue_dish vd
JOIN venues_rag v ON v.venue_id = vd.venue_id
WHERE v.geo_region LIKE '%dubai%';
-- Result: 0
```

**7c pg_description non-ASCII:** 0 rows. Live comments are ASCII.

**7d hybrid_venue_search:** live args match migration `0001` exactly (no
`geo_region` parameter -- radius-only).

## Finding -- Aug 17 2026 -- live pytest green: 280 passed

Second Step 6 run after LF-normalizing working-tree `laos*.json`:
`280 passed, 13 warnings in 58.42s`. Warnings include the five
`tests/test_supabase_integration.py` cases (DeprecationWarning from the
Supabase client) -- they ran with live creds and passed. Closes the
long-standing "five Supabase tests have never run" gap for this day.
Windows note: `git checkout -- data/*.json` alone did not clear CRLF;
explicit Python `\r\n` -> `\n` rewrite did.

## Finding -- Aug 17 2026 -- first live pytest: 270 passed, 10 failed

Step 5 real load succeeded (58 Laos venues, 30 glossary). Step 6 with
`TB_SUPABASE_URL` set: 270 passed, 10 failed, 13 warnings. The five tests in
`tests/test_supabase_integration.py` appear in the warnings list and are
absent from FAILED -- treated as ran-and-passed (R8: not skipped for missing
URL).

Failures classified:

- 8x `test_data_format` byte-identity: working-tree CRLF vs LF serializers
  (Windows `core.autocrlf`). Mitigation: `.gitattributes` `data/*.json
  text eol=lf` + renormalize on the laptop.
- `test_no_unexpected_non_ascii`: R14 arrows in DEVICE_DAY /
  ENGINEERING_RULES (fixed to `->` / `=>`).
- `test_no_silent_key_drop`: `dubai_uae_raw_snapshot.json` live-row keys
  (`created_at`, `source_url`, `trap_score`, `updated_at`). Guard now skips
  files with `not_loader_source: true`.

## Finding -- Aug 17 2026 -- Step 5 real load blocked on env name mismatch

Laos dry-runs passed (58 venues / 44 dishes; 2 expected market warnings).
Real `load_venues.py` failed at embedding: LiteLLM/OpenAI SDK required
`OPENAI_API_KEY` while `.env` carries `TB_LITELLM_API_KEY`. Real
`load_dish_glossary.py` failed looking for `TB_SUPABASE_SERVICE_KEY` while
canonical `.env.example` name is `TB_SUPABASE_KEY`. Fixed in loaders (map /
accept aliases) and DEVICE_DAY Step 5a preflight. Re-run after pull; no DB
writes from the failed venue attempt (crashed before upsert).

## Finding -- Aug 17 2026 -- empty venues_rag column dump must not unlock 0011

On device day Step 3b, `psql ... -U postgres` prompted for a password and the
piped TSV was empty (or auth noise). `device_day_name_column_decision.py`
printed `venues_rag columns: []` then `DECISION: safe to apply 0011`. That was
a false safe: the else-branch treated "neither name_local nor names_local"
as permission to apply when the real input was "no columns at all."

Action: do not apply 0011 on that output. Prefer OpenAPI Step 3a
(`device_day_schema_from_openapi.py`). Decision script now exits 2 on empty
input, password/FATAL transcripts, or missing core columns
(`venue_id` / `name` / `geo_region`). Do not pass `-U postgres` when
`TB_DATABASE_URL` already includes the role.

## Finding -- Aug 16 2026 -- Dubai loader export refused; raw dump committed

Device-day Step 2 tried `export_dubai_from_snapshot.py` then
`load_venues.py --dry-run` on `data/dubai_uae.json`. Dry-run exited non-zero
with 72 errors. Cause, verified from the committed raw dump:

- All 16 Dubai rows have null `typical_dwell_minutes`, `indoor_outdoor`, and
  `price_band` (columns present, values null).
- Categories outside the Laos-era loader set include `gallery`, `beach_club`,
  `shopping`, `attraction`, `community_space`.
- Audiences outside the set include `creative_professional`, `art_enthusiast`,
  `collector`, `food_enthusiast`.
- Vibe tag `executive` is not in `VALID_VIBE_TAGS` (though `executive` exists
  as an audience).

Decision: do not invent field values mid device-day. Commit
`data/dubai_uae_raw_snapshot.json` (`not_loader_source: true`, 6bfa1c6) for
durability, continue migrations from Step 3, and treat loader-valid
`data/dubai_uae.json` as a follow-up curation plus vocabulary decision.
The raw dump recorded `venue_dishes: 0`; confirm against the local
`live_snapshot/*/venue_dish.json` whether any Dubai dishes exist before
relying on that number.

## Finding -- Aug 14 2026 -- SPEC-04 October scope shrunk

`docs/CONSUMER_SURFACE_ROADMAP.md` said the October trip needed SPEC-09, the
driver card, and the offline vault. `docs/PROJECT_STATUS.md` omitted SPEC-04
from the numbered next list and left booking anchors at item 8. Both were
wrong relative to the forcing function ("full context" on real bookings).

Checked against what is already shipped: SPEC-02 already delivers outbox,
SyncEngine, `cache_trip` and `cache_place`. SPEC-12 already specifies the
venue driver card offline from `cache_place`. The unique SPEC-04 remainder
that matters for October is a thin rescue entry to the hotel address card
once SPEC-10 exists. `cache_vault`, pass tiles, emergency grid and phrase
packs are post-field-test. SPEC-04, PROJECT_STATUS and CONSUMER_SURFACE were
amended the same day; device-day steps live in `docs/briefs/DEVICE_DAY.md`.

## Closed since the last revision

Recorded because each was open long enough to be quoted elsewhere, and a reader
finding a stale copy of this file should be able to tell.

- **VALID_DISH_CONTAINS lived in the glossary loader.** Fixed in PR #15
  (`d061222`). Constant now lives in `config/dietary.py`; loader imports it;
  identity and set-equality guards land in `tests/test_valid_dish_contains.py`.
  The same PR also ruff-formatted the device-day helper scripts that had made
  main's format check red since `d062b5a`.
- **The loader discarded five curated fields per venue.** Fixed. The loader
  writes them and a schema-drift guard compares its write set against the
  migrations.
- **Wrong script in Lao fields.** Fixed. All three token classes are clean, and
  ten verified names carry a source and a reference.
- **Halal plus pork passed the allergen check.** Closed by retirement rather
  than by a rule. SPEC-14 retired the dietary suitability claim entirely, on
  the grounds that no source could support it. Ingredient facts remain,
  informational and disclaimed.
- **`mobility_limited` overcorrected.** The "roughly two thirds" figure was
  wrong; it is 17 of 58. The 40 of 58 figure belongs to `seniors` and the two
  were conflated.
- **The loader emitted 58 false warnings per run** about missing structured
  opening hours while its own fallback read the unstructured key. Fixed; the
  warning now fires only when both are absent, which made the two real warnings
  visible.
- **Signal provenance was computed and discarded.** `clock_skew_seconds` had
  never been persisted for any signal, leaving SPEC-02 Part C unmet in the live
  write path. Both backends now accept and store it, guarded by a test that
  drives the ingest endpoint.
- **The lint job had never passed.** See the tooling section below.

## Retracted findings

Kept because the cost of each was real and the pattern repeats.

### The pytest filterwarnings entry was not broken

A previous revision recorded as a Medium issue that `pyproject.toml` referenced
a warning class that does not exist. It does exist. The startup error came from
invoking the base compute's system pytest before installing requirements -- an
environment mistake reported as a repo defect.

What survives is smaller: naming a class in an ini `filterwarnings` entry is a
hard dependency on that class existing, and the entry only ever suppressed a
warning rather than enforcing anything. Cost: one unnecessary config change and
one over-strict version pin, both because a brief asserted something that was
not there and the executing agent matched the brief instead of contradicting
it.

### SPEC-12 was never blocked on curation

The spec claimed no Laos venue carried Lao script and that curating 58 of them
was the critical path. Both were wrong; all 58 already carried the fields. The
blocker was the loader discarding them. Cost: an instruction to the project
owner to spend days on data entry that was already done.

## Tooling incidents

### The lint job had never passed -- RESOLVED Aug 14

`ci.yml` chains lint, test, build and deploy, each needing the one before. The
lint job failed on every run as far back as the retained history, so build and
deploy never executed once in the life of the repository. The only meaningful
check was a separate `test.yml` workflow running pytest, which is why a dead
pipeline stayed invisible: pull requests showed a green test beside a red lint,
and lint was not a required check.

Causes were mundane -- a Dockerfile named with a `.py` extension that ruff
parsed as Python, deliberate late imports in tests, and a handful of real
errors. One of those real errors was a live `NameError`: `logger.info` was
called in the signal router with nothing defining `logger`.

Two lessons worth keeping. An unpinned linter install means the gate depends on
whichever version released most recently, so the pin is part of the fix. And a
formatter that wants a whole-tree reformat is not a reason to drop the gate:
the reformat goes in one isolated commit whose SHA is recorded in
`.git-blame-ignore-revs`, which both GitHub and `git blame --ignore-revs-file`
honour.

### Cloud agents are unavailable

The Databricks team enforces Privacy Mode (Legacy), which blocks cloud
subagents outright. Work needing a real Python environment therefore goes to
the execution agent; the planning side has no pytest and no ruff.

### runGit outage, Aug 11-12 -- RESOLVED

A session found `runGit` failing with `Git folder (Repo) has invalid type`
after a previous session died mid-task. Repair was a re-clone, not a retry.
The CLI allow-list refuses `repos delete`, so recovery went through the Repos
API, and re-cloning over the existing path fails until the old folder is
removed.

### Bytecode writes are denied on the compute

The same filter that blocks workspace writes also blocks bytecode caching, so
pytest fails on import there until it is run with `PYTHONDONTWRITEBYTECODE=1`.

### Half-landed documentation commit

A commit rebuilt `PROJECT_STATUS.md` only partially and left a new summary
prepended to the stale original, so the file asserted two contradictory things
about signal types. The failure was silent. This is the reason documentation
edits are verified by reading back the committed file rather than trusting the
write.
