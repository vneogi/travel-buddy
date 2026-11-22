# Genie brief: SPEC-25 trip-optional Ask (slice 2, Flutter entry)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-25-ask-anything.md`, remainder "trip-optional
Ask". Slice 1 (backend `POST /api/v1/ask`) is on main (PR #333,
`2da033c`; brief `GENIE_SPEC_25_TRIP_OPTIONAL_ASK.md` plus Amendment 1).
This slice is Flutter only. No backend change, no new dependency, no
migration, no APK request (CI and owner Windows `flutter test` are the
gate).

## 0. Owner decisions (2026-11-22)

1. Entry: an Ask bar on the Home screen that opens a new no-trip Ask
   screen.
2. Region: a picker on the Ask screen, defaulting to the region of the
   most recent trip.

## 1. Verified facts on `main` (re-verify in preflight; line numbers drift)

- Backend: `POST /api/v1/ask`, closed body `question` (1 to 500 chars
  after trim), `geo_region` (a `REGIONS` code), optional `trip_id` (any
  `trip_id` is 422 `use_trip_event`; the app never sends one). Response
  `{"ask_response": {...}}` wrapping the same envelope as the trip path:
  `answer`, `tier`, `path`, `intent`, `source_ids`, `source_class`,
  `from_cache`, `fallback_reason`, `proposal`, `food_disclaimer`,
  `what_now`. On this route `proposal` and `what_now` are always null;
  trip-only intents come back with `fallback_reason: "no_trip"`.
- Dart: `AskResponse` in `mobile/lib/data/models.dart` (around line 686)
  already parses that envelope (used by `TripEventResult`).
- Repository: `mobile/lib/data/repositories.dart` has `sendEvent` posting
  to `/trip/event` through `_api.post`. Add the new call beside it.
- Reusable widgets: `mobile/lib/features/chat/ask_entry_bar.dart`
  (`AskEntryBar(onSubmit, enabled, hintText)`), `ask_bubble.dart` (renders
  an Ask fact). Preflight: confirm `ask_bubble.dart` renders an
  `AskResponse` without a trip; record the constructor.
- Offline pattern: `mobile/lib/features/chat/chat_screen.dart` refuses
  `ask_info` offline and never enqueues (`_ChatEntry.offlineRefuse`, around
  line 449). Copy that behaviour; do not import chat-screen private types.
- Home: `mobile/lib/features/home/home_screen.dart` `build` renders a
  `ListView` with greeting, "Where to next?", the featured trip card, then
  `_CreateTripCard`. `HomeSnapshot` has `supportedRegions` (list of codes)
  and `trips` (`TripSummary` with `geoRegion`, `updatedAt`).
- Region display names exist as private maps in
  `create_trip_screen.dart` (`_displayNames`) and
  `add_booking_sheet.dart` (`_geoRegionDisplayName`). Do not refactor them.
- Routing: `mobile/lib/routing/app_router.dart` (shell routes `/`,
  `/trip/:tripId`, `/trip/:tripId/chat`, `/profile`, ...).

## 2. Change

1. Repository: `Future<AskResponse> askWithoutTrip({required String
   question, required String geoRegion})` posting `{question, geo_region}`
   to `/ask`. Never send `trip_id`.
2. Region names: add a public `regionDisplayName(String code)` in
   `mobile/lib/data/region_defaults.dart` with the same six names the
   create screen uses (Dubai, Luang Prabang, Vang Vieng, Vientiane,
   Zanzibar, Nungwi (Zanzibar)); unknown codes fall back to the code. Use
   it only in the new screen.
3. Route `/ask` (inside the same shell as `/`), screen
   `mobile/lib/features/ask/trip_optional_ask_screen.dart`:
   - Title "Ask".
   - Region picker (key `ask_region_picker`) listing
     `HomeSnapshot.supportedRegions` in server order with
     `regionDisplayName`. Default: the `geoRegion` of the trip with the
     latest `updatedAt` if that code is in `supportedRegions`; otherwise
     no selection.
   - With no region selected, the entry bar is disabled and a hint reads
     "Pick a place first."
   - `AskEntryBar` (hint "Ask about a place, food or local rules").
   - Each send shows the user's question, then the answer rendered the
     same way as a trip Ask fact (reuse `ask_bubble.dart`).
   - `fallback_reason == "no_trip"` shows the answer text plus a button
     "Start a trip" (key `ask_start_trip`) that navigates to the existing
     create-trip route. No other action.
   - Offline: refuse immediately with the same copy the trip chat uses,
     never enqueue, never call the repository.
   - Server or network error: one-line error in the thread; the bar stays
     usable.
   - Messages live in widget state only. No persistence, no thread
     history, no SQLite write (slice 3 if ever).
4. Home: an Ask bar card (key `home_ask_bar`) placed below the featured
   trip card and above `_CreateTripCard`, hint "Ask about a place". Tapping
   it navigates to `/ask`. It does not send anything itself.

## 3. Tests (must fail on main)

Flutter (`mobile/test/spec25_trip_optional_ask_test.dart`), with a fake
repository and a fake home snapshot:

1. Home shows `home_ask_bar` between the featured trip card and the create
   card; tapping it opens the Ask screen.
2. Default region is the `geoRegion` of the trip with the latest
   `updatedAt` (two trips with different regions and dates).
3. No trips: no default; the bar is disabled and shows "Pick a place
   first."; picking a region enables it.
4. Sending a question calls `askWithoutTrip` once with the question and the
   selected region, and never with a `trip_id`.
5. The answer renders through the Ask fact widget (text and source shown).
6. A `fallback_reason: "no_trip"` response shows `ask_start_trip`; tapping
   it navigates to the create-trip route.
7. Offline: sending shows the offline refusal and the fake repository is
   not called.
8. A thrown repository error shows one error line and the bar stays
   enabled.
9. Changing the region and asking again sends the new region.
10. `regionDisplayName` maps all six codes and falls back for an unknown
    code.

Existing tests: do not change expected values. Home layout tests that
count children or find widgets by position may need setup changes; list
them. Stop if more than three existing tests need expected-value edits.

R17: PR branch is one commit (or two: production, then tests). Push also:

- `feat/spec25-trip-optional-ask-flutter-r17a`: from the tip, the default
  region ignores trips (always no selection). Expected failures: 2.
- `feat/spec25-trip-optional-ask-flutter-r17b`: from the tip, the offline
  check is removed so offline sends reach the repository. Expected
  failures: 7.

The planning agent opens each as a draft PR, reads the failing test
names, closes them unmerged and deletes the branches.

## 4. Explicitly out

- Any backend change (slice 1 is on main)
- GPS, coarse location, or any permission
- Thread persistence, history, SQLite, or sync
- Suggested questions or chips
- Refactoring the existing region name maps or the trip chat screen
- Changing the trip Ask path or `ChatScreen`
- New dependencies, migrations, APK, hosted deploy

## 5. Stop rules

- Stop if `ask_bubble.dart` cannot render an `AskResponse` without a trip
  context; report what it needs.
- Stop if the shell route cannot host `/ask` without changing existing
  routes.
- Stop if more than three existing tests need expected-value edits.
- Stop if the offline check cannot be done without the trip chat's private
  types; report the alternative.

## 6. Gates

- ASCII only in added comments and strings (R14).
- No hard-coded test counts in docs (R16).
- `grep -rn '\\$' mobile/lib` after any Dart write (R1): only the two known
  price strings in `upgrade_screen.dart`.
- `flutter analyze --no-fatal-infos`: no new errors or warnings.
- No spinner left running while awaiting a sheet or route (PR #314 lesson);
  tear down `MaterialApp` before re-pumping after a popup (PR #326 lesson).
- Jobs: `flutter`, `android-compile`, `pytest`, `lint`, `postgres-proof`,
  `docker-build`, `test` green. `deploy` and `build` skipped.

## 7. PR

Branch `feat/spec25-trip-optional-ask-flutter` from the base SHA you were
sent. Do not merge. Push the branch and the two `-r17a` / `-r17b` heads.
Send the planning agent the PR description (no `gh` on Genie compute); the
planning agent opens the PRs.

The PR description must include: the preflight answers (`ask_bubble`
constructor, offline check used, shell route placement), a test-to-production
table, R17 expected failures, any existing test touched, and "no APK in
this slice". Note that the Flutter half has no local SDK if that is still
true; CI is then its first compile.
