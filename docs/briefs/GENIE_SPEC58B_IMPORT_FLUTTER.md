# Genie brief: SPEC-58 slice 1b, paste-your-plan import (Flutter)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA. The backend it depends on is merged: SPEC-58 slice 1a
(PR #375, `fbc4c0a`), SPEC-42 plain stops on busy days (PR #382,
`bb8fafe`), and the `start_empty` create flag.

Owning spec: `docs/specs/SPEC-58-paste-your-plan-import.md`. Read sections
2 (owner decisions), 3 (design rules), 4 (flow) and 5 (limits) first.

## 0. Scope in one paragraph

On the phone, a traveller pastes a plan from elsewhere. The app parses it
on device with plain rules, shows what it understood, asks the traveller to
accept or reject each catalog match, creates an empty trip, adds the
accepted and unmatched stops through one batch `import_plan` command, and
hands booking-looking lines to the existing booking sheet. The import ends
with a list of anything not imported and why.

## 1. Gate and tooling

- Flutter only, plus the small new client code it needs. No backend change,
  no schema change, no new dependency (use only what `pubspec.yaml` has).
- No APK and no hosted deploy. CI is the gate: `flutter` job (`flutter
  test` and `flutter analyze --no-fatal-infos`). Genie has no Flutter SDK
  and must not install one without owner approval, so CI is the first
  compile.
- Rules: R1 (no `\$` in Dart outside the two known price strings in
  `upgrade_screen.dart`), R14 (ASCII only in new files and docs), R16 (no
  hard-coded test counts in docs). Never print tokens or credentials.
- Do not change `ActivityCard` (stop rule 3).

## 2. Preflight (do first; report before coding)

Report answers in your first message. Stop on any section 8 rule.

1. **Create flow.** `mobile/lib/features/create_trip/create_trip_screen.dart`
   and `mobile/lib/data/repositories.dart` (`TripRepository.rangeCreate`).
   Name the screen or button where "Paste a plan" goes (the trip creation
   entry point, not a home card: SPEC-51). Confirm `rangeCreate` can take an
   optional `startEmpty` flag by adding `'start_empty': true` to the body
   only when set.
2. **Region and dates.** Confirm the region list the wizard uses (the same
   `geo_region` codes the server accepts: `config.regions.REGIONS`). The
   import needs a region and a start and end date chosen by the traveller.
3. **Event POST.** `TripRepository.sendEvent` posts `/trip/event`. Confirm
   how a 422 body is exposed to Dart (`mobile/lib/core/api_exception.dart`
   surfaces `detail.message`). The import needs the full `detail.results`
   too, so confirm where that body can be read.
4. **Catalog match client.** There is no Dart client for `POST
   /trip/catalog_match` yet. Confirm the shape in `models/schemas.py`
   (`CatalogMatchRequest`, `CatalogMatchResponse`). Add a repository method
   that sends only `{geo_region, names}`.
5. **Booking sheet.** `mobile/lib/features/booking/add_booking_sheet.dart`
   (`AddBookingSheet`) and `extractBookingFromText` in `booking_parser.dart`.
   Confirm a new optional `pastedText` constructor parameter can prefill the
   sheet from `extractBookingFromText` without changing existing callers.
6. **Plain-row actions.** The SPEC-45 place detail (`activity_detail_screen.dart`)
   shows Open in Maps, Driver card, Swap, Skip or Cancel, Move, and Love. For
   a plain row (`venueId` null, `placeSource` trip_private, no coordinates)
   confirm which actions the server supports: Move and Cancel yes; Swap no
   (no catalog candidates); rename no (there is no rename endpoint).
7. **Tests.** Existing `spec45_place_detail_test.dart`, `spec42_*` and
   `spec58` (none yet) tests that must pass unchanged.

## 3. Build

### 3.1 Parser (pure Dart, no I/O, no clock)

New file `mobile/lib/features/paste_plan/plan_parser.dart`.

- Input: raw text, trip start and end dates (ISO dates, passed in), the
  region code. Output: an ordered list of days, each with stop lines
  (`name`, optional `clockTime`, optional `note`), a `bookingLines` list, and
  a `notUnderstood` list.
- Day headings: "Day N" (N counted from the trip start), a weekday-plus-date
  line, or a bare date inside the span. A heading outside the span goes to
  `notUnderstood` with its text, never silently mapped.
- Stop lines: an optional leading clock time ("9:00", "09:30", "9.30 am",
  "11am", "2pm"), then a name, optionally followed by " - " or " (" and a
  note. Strip bullets and numbering ("1.", "-", "*").
- Booking-looking lines (flight code, "confirmation", "reservation",
  "check-in", "check-out", "booking ref"): into `bookingLines`, not stops.
- Limits, checked before any network call: at most 60 stop lines and 14
  day headings. Over the limit: refuse with a message; import nothing.
- Clock-time to slot hint (client-side, mirrors server `slot_from_time`
  windows): before 11:00 `morning_tour`; 11:00 to 13:59 `lunch`; 14:00 to
  16:59 `afternoon_evening_tour`; 17:00 and later `dinner`. A pasted time is
  a hint: the server's checks decide.
- Tests for every branch above, with fixtures in
  `mobile/test/fixtures/spec58/` (new files, ASCII only): a chatbot-style
  three-day paste, an agent-style paste with bookings, and a blog-style list
  with notes and bad lines.

### 3.2 Match step

- One call to `POST /trip/catalog_match` with `{geo_region, names}`. Names
  are the trimmed stop names only. Never send the raw paste, never send
  notes, clock times or booking lines.
- Requires network. Offline: refuse the step with the existing offline
  banner pattern; nothing is queued, nothing is sent later (SPEC-58 section
  3, and the signal outbox is not used for this flow).
- Each stop shows: a suggested catalog match (name, city, provenance) or
  "Not in our catalog". `near` suggestions are shown for the traveller to
  pick from. Default state of every match is UNCONFIRMED.
- The traveller accepts or rejects each stop. Rejected or unmatched stops
  become plain rows. Exact matches are not auto-accepted.

### 3.3 Review screen

- Shows the parse: days in order, stops with their match decision and
  clock-time hint, "Not understood" lines (not imported), booking lines
  (routed to 3.5).
- Every plain row needs a stay length: chips 15, 30, 45, 60, 90, 120
  minutes, the traveller's own statement (never a catalog guess). Commit is
  disabled until every plain row has one.
- A stop with no clock time and no slot chosen gets slot chips
  (`morning_tour`, `lunch`, `afternoon_evening_tour`, `dinner`). A stop with
  a day that is outside the trip span is blocked until the traveller moves it.
- Nothing is committed until the traveller presses Create trip. Accepting a
  match is not commitment.

### 3.4 Commit (the order matters)

1. `TripRepository.rangeCreate(..., startEmpty: true)` with the chosen
   region, start and end dates, a solo party of size 1, no interests. The
   server creates empty days (SPEC-58a / Amendment 1).
2. One `sendEvent(type: EventType.addActivity, preferences: {mode:
   'import_plan', items: [...]})`. Items are sorted by date, then slot, then
   list order. Each catalog item is `{kind: 'catalog', venue_id, target_date,
   target_slot}`. Each plain item is `{kind: 'plain', name, target_date,
   target_slot, typical_dwell_minutes}`. The `name` and dwell are the
   traveller's; no clock time is sent as a time.
3. Success (200): read `import_results`. Each `added` result becomes a
   placed stop. Each `refused` result goes to the "Not imported" list with
   its `message`.
4. Every item refused (422 `import_plan_refused`): read
   `detail.results`, show the "Not imported" list, and keep the empty trip.
   No retry loop.
5. Booking lines: after the trip exists, open `AddBookingSheet` once per
   booking line with `pastedText` prefilled (3.5). The traveller saves or
   skips each one. Nothing is saved without their confirmation.
6. Result screen: counts of added, not imported, and booking saved, with
   the "Not imported" list and a Copy action (Clipboard) that copies the
   names, days and reasons so nothing is lost.

### 3.5 Booking lines

- Route each booking line to the existing SPEC-10 provider-aware paste:
  `extractBookingFromText(line, importSource: ...)`, then `AddBookingSheet`
  with `pastedText` prefilled. Do not write a second booking parser.
- `AddBookingSheet` gets one new optional `pastedText` parameter. Existing
  callers are unchanged.

### 3.6 Plain rows on the itinerary and detail

- A plain row is `venueId == null` and `placeSource == trip_private`
  (existing fields). It shows the label "Not in our catalog, travel time not
  checked" on the place detail screen (`activity_detail_screen.dart`) and in
  the import result. Do not change `ActivityCard` (stop rule 3).
- On the place detail for a plain row: hide Open in Maps and Driver card
  (the Driver card path needs a catalog id; a map search by name is an open
  owner decision, so default to hidden). Show Move and Cancel (the server
  supports both). Hide Swap and Love only if preflight 6 shows they cannot
  work for a plain row; otherwise keep Love as it is.
- No rename action. Rename needs an endpoint that does not exist (stop 4).

## 4. Tests

New file `mobile/test/spec58_paste_plan_test.dart`. Use a fake `ApiClient`
that records every request body. Cover at least:

1. Chatbot-style three-day paste parses to the expected days and stops in
   order (match a fixture expected output).
2. An agent-style paste routes flight and hotel lines to `bookingLines`, not
   to stops.
3. A blog-style paste with bad lines puts those lines in `notUnderstood`
   without dropping valid stops.
4. Clock-time to slot hint: 10:59 morning, 11:00 lunch, 13:59 lunch, 14:00
   afternoon, 16:59 afternoon, 17:00 dinner (the boundaries are the test).
5. Empty paste, paste over 60 stops and paste over 14 days are refused with
   no network call (the fake records zero requests).
6. Catalog match: the request body contains only `geo_region` and `names`.
7. Raw paste text, clock times, notes and booking lines appear in no request
   body (assert on every recorded request).
8. No commit before the traveller presses Create trip: zero `rangeCreate`
   or `sendEvent` calls while on the review screen.
9. A rejected match becomes a plain row, and a plain row without a stay
   length blocks Create trip.
10. Create trip calls `rangeCreate` with `startEmpty: true` and then one
    `import_plan` event with items sorted by date, slot and list order.
11. A 200 response shows added stops; a 422 `import_plan_refused` shows the
    "Not imported" list with each reason and leaves no partial state.
12. Booking lines open `AddBookingSheet` with `pastedText` after the trip is
    created, one per line, and nothing saves without confirmation.
13. A plain row's place detail shows the "Not in our catalog, travel time not
    checked" label and has no Open in Maps and no Driver card action.
14. Move and Cancel work on a plain row through the existing event calls.
15. Offline: the match step refuses with the offline banner and sends nothing.
16. The Copy action copies names, days and reasons, and no other data.

Existing tests (`spec45_place_detail_test.dart`, `spec45_friction_test.dart`,
`spec42_*`, `spec10_*` booking tests) must pass unchanged. Do not edit them.
If one must change, stop (stop rule 6).

Harness rules: capture Riverpod locals before awaits; use an in-memory
database if one is needed; `tester.runAsync` for async; no
`pumpAndSettle` on screens that have a spinner or a timer.

## 5. Pull request and R17

- Branch: `feat/spec58b-import-flutter` from current `origin/main`.
- Title: `feat(spec58b): paste-your-plan import (Flutter)`.
- PR body: preflight answers 1 to 7, the test-to-production table, the
  exact list of existing tests touched (should be none), and a line saying
  there is no backend, schema, dependency or deploy change.
- Push three R17 sabotage branches, one commit each from the feature head,
  and state the expected failing tests:
  - `-r17a`: the match step auto-accepts every match (expect test 8 and
    test 9's accept path).
  - `-r17b`: the raw paste text is added to the `import_plan` request body
    (expect test 7).
  - `-r17c`: a plain row shows Driver card (expect test 13).
  Branch names: `feat/spec58b-import-flutter-r17a`, `-r17b`, `-r17c`.
- Do not merge and do not open PRs; the planning agent opens them and reads CI.
  If a sabotage fails tests other than the ones named, say so.

## 6. Non-goals

- Backend or schema changes; any new endpoint; rename.
- Map launch by name for plain rows (owner open decision).
- Outcome signals for accepted or rejected matches (SPEC-43 first).
- Offline queueing of the import.
- PDF, screenshot or OCR input (SPEC-39 stays deferred).
- Party or group context (SPEC-54), transfer cards (SPEC-55).
- Changing `ActivityCard`, the scheduler or any existing booking rule.

## 7. Dependencies on merged code (do not change)

- `POST /trip/catalog_match` (PR #375). Request `{geo_region, names}`
  (1 to 60 names, 2 to 80 characters each). Response `{results: [{name,
  match, near}]}`.
- `POST /trip/event` `add_activity` with `preferences.mode == 'import_plan'`
  and `items` (1 to 60). Success returns `import_results`; all-refused
  returns 422 `import_plan_refused` with `detail.results`.
- `POST /trip/create` with `start_empty: true` (range create only; other
  shapes refuse 422 `start_empty_unsupported`).
- Plain stops with no coordinates on busy days (PR #382): accepted by the
  server, placed at the slot start with no travel check.

## 8. Stop rules (write a question, do not widen scope)

Stop and report, quoting the preflight line, if:

1. A change to `ActivityCard` is the only way to show the plain-row label.
2. A new endpoint, a rename, or a schema change is needed for any action.
3. Any change to `ActivityCard`, the scheduler or a booking rule is needed.
4. Rename or any other action the server does not support is required.
5. A map launch by name is needed for plain rows (owner decision pending).
6. Any existing test must change to pass.
7. The `AddBookingSheet` change would alter existing callers.
8. A new dependency or a Flutter SDK install is needed.

## 9. Report format

End with: PR-ready branch and head SHA; preflight answers 1 to 7; the
test-to-production table; the three R17 branch heads and their expected
failing tests; any stop rule hit.
