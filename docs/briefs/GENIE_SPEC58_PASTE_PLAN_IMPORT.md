# Genie brief: SPEC-58 paste-your-plan import, slice 1

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-58-paste-your-plan-import.md`. Read it
first. The owner decisions in its section 2 are binding for this slice.

## 0. Scope in one paragraph

A traveller pastes a plan from elsewhere. The app parses it on device
with plain rules, shows the parse, asks the traveller to confirm each
catalog match, sends booking-looking lines to the existing SPEC-10 paste,
and adds accepted stops through the existing typed Add path. Unmatched
stops become plain "Not in our catalog" rows that recovery never uses.

## 1. Gate and tooling

- Flutter and backend changes are allowed. Schema changes, migrations and
  new dependencies are not (see section 8).
- No APK and no hosted deploy. CI is the gate, including the `flutter`
  job (`flutter test` and `flutter analyze --no-fatal-infos`).
- Do not install Flutter without owner approval.
- Rules that apply: R1 (no `\$` in Dart outside the two known price strings
  in `upgrade_screen.dart`), R14 (ASCII only in new files and docs), R16
  (no hard-coded test counts in docs).

## 2. Preflight (do first; report before coding)

Check each item on current `main` and report the answers in the PR body.
If an answer breaks a stop rule in section 8, stop and report.

1. **Typed Add path.** Find the existing typed Add for a catalog venue
   (SPEC-10 / SPEC-40 / SPEC-41 code). Confirm it can take a catalog venue
   id and a day, and that the server validates hours and reachability.
   Record the endpoint and request shape.
2. **Catalog match source.** Find how the app already loads or searches
   region venues (`list_venues_for_region`, SPEC-32; `searchVenues`,
   SPEC-34). Confirm whether a name-only lookup exists. If it does not,
   stop (section 8, first bullet).
3. **SPEC-10 paste entry.** Find the provider-aware booking paste
   (`fc6926b`). Confirm it can be called with one booking-looking line,
   or the whole text, from a new screen.
4. **Node model for plain rows.** Look at `TripNode`
   (`mobile/lib/data/models.dart`) and `nodeKind`. Confirm a plain row can
   be represented with existing fields (no catalog id, no slot, no hours,
   no coordinates). If it needs a new field, stop.
5. **Exclusion points.** Find where What Now, swap candidates and the
   Driver card read the itinerary. Confirm a plain row can be excluded in
   one place each, without a scheduler rule change.
6. **Existing tests.** List tests that assume every itinerary node has a
   catalog id. These must still pass unchanged.

## 3. Build (slice 1)

### 3.1 Parser (pure Dart, no network)

New file `mobile/lib/features/paste_plan/plan_parser.dart`.

- Input: raw text. Output: ordered days, each with stop lines, plus a
  "Not understood" list and a "Looks like a booking" list.
- Day headings: lines naming a day or date ("Day 2", "Tuesday 12 Dec",
  "2 Dec"). Stop lines: an optional leading time ("9:00", "09:30 am",
  "11am") then a name, with an optional trailing note.
- Booking-looking lines: contain a flight code (two letters, digits), a
  confirmation or reservation word, or a check-in or check-out phrase.
- Limits: 60 stop lines, 14 day headings. Over the limit: refuse, no
  partial import.
- Pure function: no I/O, no clock reads (take the trip's dates as input).

### 3.2 Match step

- For each stop name, look for a catalog match using the source found in
  preflight item 2. Send only the stop name and the trip's region. Never
  send the raw paste.
- A match is a suggestion. Show name, city and provenance. Default state
  is unconfirmed. No auto-accept.
- Rejected or no match: the stop becomes a plain row.

### 3.3 Commit

- Accepted matches: call the typed Add path (preflight item 1) for the
  chosen day. Show each server refusal on its row with the reason.
- Plain rows: a local node with no catalog id, no slot, no hours, no
  coordinates, and the name the traveller saw in the paste.
- Booking-looking lines: pass to the SPEC-10 paste entry (preflight 3);
  do not parse them here.

### 3.4 Plain-row behaviour

- Label "Not in our catalog". No map button, no Driver card button, no
  hours row, no slot row.
- Actions: rename, move to another day, delete.
- Excluded from What Now candidates, swap candidates and Driver card
  (preflight 5). Included in the day list and the text export.

### 3.5 Entry point

- One "Paste a plan" action on the trip creation surface and on the
  itinerary's overflow. Do not add a home card (SPEC-51).

## 4. Tests

Add `mobile/test/spec58_paste_plan_test.dart` with these cases. Use fixtures
under `mobile/test/fixtures/spec58/` (new files, ASCII only).

1. Chatbot-style three-day paste parses to the right days and stops in
   order (match a fixture expected output).
2. Booking-looking line goes to the booking list, not the stop list.
3. Unmatched stop becomes a plain row: no hours, no map button, no Driver
   card button.
4. A suggested match is not committed until accepted. Rejected becomes a
   plain row.
5. Accepted match calls the typed Add path once; a server refusal shows
   its reason on the row.
6. Empty paste and an over-limit paste are refused with no network call.
7. Raw paste text does not appear in any request body or log line (assert
   on the fake client's recorded calls).
8. Plain rows are absent from the What Now and swap candidate lists.

Do not change existing tests. If an existing test must change to pass,
stop and report (section 8).

## 5. Pull request

- Branch: `feat/spec58-paste-plan`, from current `origin/main`.
- Title: `feat(spec58): paste-your-plan import slice 1 (Flutter)`.
- PR body: preflight answers (section 2), the test-to-production table,
  any file outside `mobile/` (should be none except docs), and the exact
  list of existing tests you touched (should be none).
- Also open three R17 sabotage branches, each as a separate commit on a
  branch from the feature head, and report their expected failing tests:
  - `-r17a`: remove the plain-row exclusion from What Now (expect test 8).
  - `-r17b`: remove the "Not in our catalog" label (expect test 3).
  - `-r17c`: commit suggested matches without acceptance (expect test 4).
  Branch names: `feat/spec58-paste-plan-r17a`, `-r17b`, `-r17c`.
- Do not merge anything. The planning agent opens the PRs and reads CI.

## 6. Stop rules (write a question, do not widen scope)

Stop and report, with the exact preflight line, if:

- there is no name-only catalog lookup and adding one would send more
  than the stop name;
- a plain row needs a new backend field, a migration or a schema change;
- raw paste would need to be stored or sent anywhere;
- booking routing needs a second parser;
- a test can only pass by changing a SPEC-41 or SPEC-10 check, or by
  editing an existing test;
- the work needs a new dependency.

## 7. Non-goals (do not build)

- LLM parsing, LLM-written schedules, or any model call.
- Long-tail or OSM places, or a "not in catalog but recommended" list.
- Auto-accepting any match.
- PDF, screenshot or OCR input.
- Outcome signals for accepted or rejected matches.
- Party or group context (SPEC-54), transfer cards (SPEC-55), map launch
  for plain rows.

## 8. Report format

End your report with: PR number and head SHA; preflight answers 1-6; the
test-to-production table; the R17 branch heads; any stop rule hit. Do not
paste tokens or credentials anywhere.
