# Genie brief: SPEC-43 client privacy remainders (Flutter)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-43-security-privacy-and-data-governance.md`,
remainders of Gap 5 (client: booking references masked by default) and
Gap 7 (client: optional signals are not queued without a grant). Parent
rules: SPEC-02 outbox (`mobile/lib/offline/offline_database.dart`,
`mobile/lib/offline/sync_engine.dart`), server consent gate
(`services/consent.py`, `routers/signal_router.py` about line 395).

This slice is Flutter only. No backend change, no SQLite schema change, no
migration, no new dependency, no APK, no hosted deploy. The gate is CI and
owner Windows `flutter test`. Do not install Flutter without owner approval.

## 0. Owner decisions (2026-11-23)

1. Screenshots and the task switcher: NOT blocked in this slice. No
   FLAG_SECURE. The spec calls screenshot policy a product decision; the
   owner deferred it. Do not add FLAG_SECURE or any window-secure call.
2. Optional signals: until a consent screen and a grant ledger exist, the
   client does NOT queue optional signal types. Places loved stay on the
   device exactly as they are today (the local loved state is untouched);
   only the outbox row is skipped.

## 1. Verified facts on `main` (re-verify in preflight; line numbers drift)

Gap 5 (masking):
- `mobile/lib/features/booking/add_booking_sheet.dart`: the confirmation
  code is a plain `TextField` bound to `_codeController` (about line 615,
  label "Confirmation Code"). It is pre-filled in edit mode (about line 92)
  and set from the paste parser (about line 219). The paste field is
  `_pasteController` (about line 631, title "Paste confirmation text").
- Android: `allowBackup="false"`, `fullBackupContent` and
  `dataExtractionRules` are declared, and the rules exclude the database and
  shared prefs for cloud backup and device transfer. Already landed. Do not
  change them.
- SQLCipher is in `pubspec.yaml` (`sqflite_sqlcipher`). Already landed.
- No code masks or hides any booking reference today.

Gap 7 (optional signals):
- `mobile/lib/services/signal_service.dart`: `emit` (about line 96) writes
  every signal to the outbox through `_db.enqueue` before any network call.
  No consent check exists on the client.
- The optional personalization types emitted by the app are `user_loved`
  (`emitUserLoved`, called from `mobile/lib/features/itinerary/itinerary_screen.dart`
  about lines 481 and 524), `reroute_accepted` and `reroute_rejected`
  (`emitRerouteAccepted`/`emitRerouteRejected`, itinerary_screen about lines
  118 and 130). `dish_loved` and `dish_ordered` are defined in the service
  but not called from the UI in preflight; confirm.
- The server's map in `services/consent.py` (`SIGNAL_PURPOSE`) puts
  `user_loved`, `dish_loved`, `dish_ordered`, `reroute_accepted` and
  `reroute_rejected` under `PURPOSE_PERSONALIZATION` (optional). With no
  grant ledger they are always rejected, `sync_engine.dart` marks them
  `failed_permanent` (about line 172), and the only place that shows it is
  the debug screen `sync_status_screen.dart`. So today these taps are lost
  silently.
- Necessary types stay queued: `node_skipped`, `visited_confirmed`,
  `driver_card_shown`, `name_confirmed`, `prompt_dismissed`, `booking_added`,
  `session_start`. Do not gate them.
- The love tap in `itinerary_screen.dart` calls `emitUserLoved` and then
  `markLoved` (controller). The local loved state must still update whether
  or not the signal is queued. Preflight: confirm nothing reads the signal
  path to decide the loved state.

## 2. Change

Part A, booking references masked by default (Gap 5):
1. In `add_booking_sheet.dart`, the confirmation code field renders
   obscured by default (`obscureText: true`) with a visibility toggle
   (an `IconButton` with a tooltip, key `booking_code_reveal`). Tapping it
   reveals the text; tapping again hides it. The reveal state resets to
   hidden each time the sheet opens.
2. The same masking applies to any other place the sheet displays the code
   after parsing (the extraction review step, if it shows it). Preflight
   must list every such place; mask each one.
3. The paste text field is not changed. Preflight must confirm the raw paste
   text is held only in memory and is not written to SQLite, shared prefs,
   a file or a log. If it is written anywhere, stop and report; do not fix
   it in this slice.

Part B, optional signals are not queued (Gap 7):
4. Add one constant in `signal_service.dart`:
   `kOptionalSignalTypes = {'user_loved', 'dish_loved', 'dish_ordered',
   'reroute_accepted', 'reroute_rejected'}`. It mirrors the server's
   `PURPOSE_PERSONALIZATION` set; add a comment that says so and that the
   server map is the authority.
5. In `emit`, before `_db.enqueue`: if `signalType` is in the set, return
   without enqueueing. No error, no UI message, no log at error level. A
   `debugPrint` is allowed.
6. Keep the public method signatures. `emitUserLoved` and the reroute
   methods keep their current behaviour from the caller's side.
7. Do not change the necessary types, the server, the outbox schema, or the
   sync engine.

## 3. Tests (must fail on main unless noted)

Flutter, `mobile/test/spec43_client_privacy_remainders_test.dart`:

1. The confirmation code field renders obscured on open (edit mode with a
   stored code). Fails on main.
2. Tapping the reveal control shows the code; tapping again hides it. Fails
   on main.
3. `emitUserLoved` writes no outbox row (count before and after is equal).
   Fails on main.
4. `emitRerouteAccepted` and `emitRerouteRejected` write no outbox rows.
   Fails on main.
5. `emitNodeSkipped` and `emitVisitedConfirmed` still write one outbox row
   each. Passes on main; guard.
6. Tapping love on an itinerary card still shows the place as loved and
   writes no outbox row. Fails on main on the outbox assertion.
7. A paste parse with a code does not write the paste text or the code to
   the database (asserts on the outbox and the local tables the sheet
   touches). Passes on main; guard.

Existing tests: `durable_hearts_test.dart` (around line 138),
`spec43_g6_signout_test.dart` (around lines 105 and 259) and
`offline_sync_test.dart` build or assert `user_loved` signals. Preflight
lists every existing test that expects an outbox row from an optional
emit. Change only those expected values that are directly about the
outbox row for an optional type, and say so in the PR. Stop if more than
three existing tests need edits, or if any test asserts that a love
reaches the server.

R17 (branches from the tip, each pushed as its own head):
- `feat/spec43-client-privacy-r17a`: the `emit` gate is removed, so
  optional types enqueue again. Expected failures: tests 3, 4 and 6.
- `feat/spec43-client-privacy-r17b`: the obscure default is removed, so the
  field renders in clear text. Expected failures: test 1.
- `feat/spec43-client-privacy-r17c`: the gate also blocks necessary types.
  Expected failures: test 5.

The planning agent opens each as a draft PR, reads the failing names,
closes them unmerged and deletes the branches.

## 4. Explicitly out

- The consent screen, the grant ledger, withdrawal, notice versions, age
  bands and any server consent change. These are a later brief after the
  owner and counsel settle the wording and the purpose list.
- FLAG_SECURE, screenshot blocking and task-switcher hiding (owner deferred)
- Masking the raw paste textbox or the trip itinerary cards
- Gap 4 Flutter leave, Gap 12 lock-screen, iOS, ProGuard (`isMinifyEnabled`
  is false today; separate brief)
- Changing the outbox schema, sync engine retry rules or failed-row purge
- Any backend change, migration, dependency, APK or hosted deploy

## 5. Stop rules

- Stop if the paste text, or the confirmation code, is written to disk or a
  log somewhere other than the sheet's own in-memory state.
- Stop if the love path reads the signal queue to decide the loved state.
- Stop if the server map and the client constant disagree on any optional
  type when you compare them. Report the difference; do not decide.
- Stop if more than three existing tests need edits, or if any existing test
  needs a change beyond expected outbox rows for optional types.
- Stop if the masking would need a new dependency.

## 6. Gates

- ASCII only in added code, comments and strings (R14).
- No hard-coded test counts in docs (R16).
- `grep -rn '\\$' mobile/lib` after any Dart write (R1): only the two known
  price strings in `upgrade_screen.dart`.
- `flutter analyze --no-fatal-infos`: no new errors or warnings.
- Jobs: `flutter`, `android-compile`, `pytest`, `lint`, `postgres-proof`,
  `docker-build`, `test` green. `deploy` and `build` skipped.

## 7. PR

Branch `feat/spec43-client-privacy-remainders` from the base SHA you were
sent. Do not merge. Push the branch and the three `-r17a` / `-r17b` /
`-r17c` heads. Send the planning agent the PR description; the planning
agent opens the PRs.

The PR description must include: the preflight answers (every place the
code is shown, the paste-storage check, the love path check, the list of
existing tests that expect an optional outbox row, and the server and client
map comparison), a test-to-production table, R17 expected failures, every
existing test touched and why, and "no APK and no hosted deploy in this
slice". Say that the phone check is later.

## Amendment 1 (2026-11-23, after Genie preflight)

Genie's preflight triggered two stop rules and found a naming mismatch.
The owner's planning agent decided all three; build on this basis.

1. Stop rule "code written to disk": the confirmation code is stored in the
   `cache_trip` table through `TripNode.toJson` (`mobile/lib/data/models.dart`
   about line 141, written by `ItineraryController.load` and
   `_cacheUpdatedTripNodes`). That table lives in the offline SQLite store,
   which opens with SQLCipher on Android and iOS
   (`mobile/lib/offline/offline_database.dart` `_open`, via
   `openOfflineStore`) and is excluded from backup and device transfer
   (`mobile/android/app/src/main/res/xml/data_extraction_rules.xml`). SPEC-43
   Gap 5 says to keep booking references local and encrypted, so this is
   ACCEPTED and out of scope. Do not change `cache_trip` contents or
   `TripNode.toJson`. Web and desktop builds stay unencrypted, as already
   recorded in the code comment; that is unchanged and not this slice.
   The stop rule still applies to anything else: a log, a file, shared
   preferences, the outbox, or the raw paste text anywhere on disk.
2. Two existing tests use `user_loved` only as a sample type to exercise the
   outbox: `mobile/test/signal_service_test.dart` ("emit enqueues to outbox
   with correct payload shape", about line 93) and
   `mobile/test/offline_sync_test.dart` ("1. emit persists to outbox before
   network", about line 56). Option A is approved: change only their sample
   signal type from `user_loved` to the necessary type `visited_confirmed`,
   with the payload assertions updated to that type. It is a setup change;
   the behaviour under test (one pending row, correct payload shape, durable
   before network) is unchanged. List both in the PR description.
   `durable_hearts_test.dart` "restore does not enqueue another signal" needs
   no edit; leave it and note in the PR that it now compares 0 and 0.
   These two tests do not count toward the three-test stop limit; any other
   existing test that needs an edit still does.
3. Branch names: the correct names are
   `feat/spec43-client-privacy-remainders`,
   `feat/spec43-client-privacy-remainders-r17a`,
   `feat/spec43-client-privacy-remainders-r17b` and
   `feat/spec43-client-privacy-remainders-r17c`. Section 3's shorter names
   are replaced by these.
