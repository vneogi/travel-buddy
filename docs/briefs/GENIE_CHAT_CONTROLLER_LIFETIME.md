# Genie brief: chat keeps the itinerary controller alive (What Now error fix)

Read this whole file before touching anything. It is the complete job.
If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

This brief is reproduce-first. You must prove the bug in a failing test
on the unmodified base before you change any `lib/` file. If the
reproduction does not fail, stop and report. Do not fix on a guess.

## 0. Context

Hosted logs on 2026-11-16 (recorded in `docs/HOSTED_STATE.md`): two What
Now form sends showed "I could not complete that request. Please try
again." while Cloud Run returned HTTP 200 with a normal-sized body. Each
failing POST overlapped a `GET /api/v1/trip/{id}`, and neither was
followed by the `GET /api/v1/user/status` that a successful send
triggers.

Planning read of `main` (unproven until your test reproduces it):

1. `itineraryControllerProvider` in
   `mobile/lib/features/itinerary/itinerary_notifier.dart` is
   `StateNotifierProvider.autoDispose.family`. The constructor calls
   `load()`, which does `GET /trip/{id}`.
2. `TripEventService.sendEvent` (`tripEventProvider`, same file) does
   `_ref.read(itineraryControllerProvider(tripId).notifier).applyEvent(...)`.
   A `read` does not keep an autoDispose provider alive.
3. `ChatScreen` (`mobile/lib/features/chat/chat_screen.dart`) only
   `ref.read`s the controller. It never watches or listens to it.
4. The comment above `tripEventProvider` assumes the itinerary screen is
   always mounted under chat. That is false: Home's trip card has an
   "Ask about this trip" icon that does
   `context.push('/trip/<id>/chat')` (`home_screen.dart`), and in
   `app_router.dart` the chat route is a sibling of `/trip/:tripId`
   inside the `ShellRoute`, not a child.
5. So when chat is opened from Home, each send creates a fresh
   controller (firing `GET /trip`), Riverpod disposes it during the
   POST, `applyEvent` hits `if (!mounted) return null;` after the
   await, and chat renders the generic error. The success-only
   `_ref.invalidate(userStatusProvider)` never runs. This matches both
   log signals.
6. Every existing chat widget test overrides `tripEventProvider` with a
   mock, so the real controller lifetime was never exercised.

## 1. Goal

While a `ChatScreen` is mounted, it holds one live listener on
`itineraryControllerProvider(widget.tripId)`, so sends from chat always
reach a live controller, however chat was opened. The listener is
closed when chat is disposed, so the controller is still released when
nothing else needs it.

Behaviour that must not change: the autoDispose provider type, the
`applyEvent` body (including its `!mounted` early return), routing, Home,
the itinerary screen, and every existing test assertion.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm on that SHA: `itineraryControllerProvider` is
   `StateNotifierProvider.autoDispose`; `ChatScreen` has no
   `ref.watch`, `ref.listen` or `ref.listenManual` of
   `itineraryControllerProvider`; Home pushes `/trip/<id>/chat`. If any
   differs, stop and report.
3. Confirm `mobile/test/chat_controller_lifetime_test.dart` and
   `origin/fix/chat-controller-lifetime` do not exist.
4. Branch: `fix/chat-controller-lifetime`.

## 3. Read before editing

- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `docs/specs/SPEC-46-what-now-foreground-context.md` (What Now in chat)
- `mobile/lib/features/itinerary/itinerary_notifier.dart` (whole file)
- `mobile/lib/features/chat/chat_screen.dart` (`initState`, `_send`,
  `_sendWhatNow`, `_openWhatNowSheet`, the Ask-to-Add path that calls
  `load()`)
- `mobile/lib/routing/app_router.dart`, `mobile/lib/features/home/home_screen.dart`
- `mobile/test/itinerary_controller_test.dart` (ProviderContainer
  harness and the `ready()` comment about autoDispose)
- `mobile/test/spec46_what_now_test.dart` and
  `mobile/test/spec25_ask_envelope_test.dart` (ChatScreen harness; note
  they mock `tripEventProvider`, which your new widget tests must NOT do)

## 4. Files you may touch

- `mobile/test/chat_controller_lifetime_test.dart` (new)
- `mobile/lib/features/chat/chat_screen.dart`: add the listener in
  `initState`, close it in a `dispose` override. Nothing else in this
  file.
- `mobile/lib/features/itinerary/itinerary_notifier.dart`: the comment
  above `tripEventProvider` only (make it true: chat holds its own
  listener; Home can open chat with no itinerary underneath). No code
  change in this file.

Nothing else. No backend, no docs (the planning agent owns docs), no
router, no Home, no itinerary screen, no `pubspec`, no Riverpod upgrade.

## 5. Step 1: reproduce on the unmodified base

Write the new test file first (section 7, tests 1 to 3) and run it with
`lib/` untouched.

Expected on the base:

- test 1 passes (it documents the mechanism: a send with no live
  listener returns null);
- tests 2 and 3 FAIL (the generic error text is shown instead of the
  server answer).

Record the exact failure lines for tests 2 and 3 for the report.

Stop and report, without touching `lib/`, if:

- test 1 does not return null on the base (the mechanism is wrong); or
- test 2 or test 3 passes on the base (the bug did not reproduce).

## 6. Step 2: the fix

In `_ChatScreenState`:

- a field `ProviderSubscription<ItineraryState>? _itinerarySub;`
- in `initState`, after `super.initState()`:
  `_itinerarySub = ref.listenManual(itineraryControllerProvider(widget.tripId), (_, __) {});`
- add `dispose()` that calls `_itinerarySub?.close();` then
  `super.dispose();`

Do not use `ref.watch` in `build` for this: chat must not rebuild on
every itinerary state change. Do not make the provider non-autoDispose
(that would keep every visited trip's controller alive for the app
session). Do not change `applyEvent`'s `if (!mounted) return null;`:
returning a result from a disposed controller would let the itinerary
screen's swap path use `ref` after its widget is gone.

Side effect you should expect and may note in the report: opening chat
from Home now loads the trip once on open, so the What Now sheet's
default context stop can come from real nodes instead of an empty
fresh controller.

## 7. Tests

`mobile/test/chat_controller_lifetime_test.dart`, exact names. No
network. Use mocktail fakes for `TripRepository` and the offline
database the same way the existing tests do. In the widget tests, do
NOT override `tripEventProvider`; override `tripRepoProvider`,
`offlineDatabaseProvider` (a real in-memory DB or a mock, as the
existing chat tests do) and `identityCacheScopeProvider` only. Make
`repo.sendEvent` complete from a `Completer` so the request is still
pending while frames and microtasks run.

1. `send through tripEventProvider with no live itinerary listener returns null`
   ProviderContainer only. Start
   `container.read(tripEventProvider).sendEvent(...)`, let microtasks
   and a short delay run, complete the Completer with a valid
   `TripEventResult`, then expect null. This documents why chat must
   hold a listener. It passes before and after the fix.
2. `chat opened without itinerary shows the server answer, not the generic error`
   Pump `ChatScreen` as the app home (no itinerary screen), send a typed
   question, pump while the request is pending, complete the Completer
   with a result whose `askResponse` carries a known answer, settle.
   Expect the known answer text and no "I could not complete that
   request" text. Fails on the base; passes after the fix.
3. `chat What Now form opened without itinerary shows the What Now result`
   Same setup, but use the What Now sheet submit path that
   `spec46_what_now_test.dart` already drives, with a result carrying a
   `whatNow` payload. Expect the What Now result bubble and no generic
   error text. Fails on the base; passes after the fix.
4. `chat keeps one itinerary controller for its lifetime`
   Chat opened without itinerary; complete two sends in a row. Expect
   `repo.getTrip(tripId)` called exactly once.
5. `closing chat releases the itinerary controller`
   After the chat widget is removed from the tree and frames are
   pumped, `container.exists(itineraryControllerProvider(tripId))` is
   false. Get the container with `ProviderScope.containerOf` or pump
   with an `UncontrolledProviderScope` you own.
6. `chat opened over a live itinerary listener shares that controller`
   Before pumping chat, hold `container.listen(itineraryControllerProvider(tripId), ...)`
   to stand in for the itinerary screen. A chat send whose result has
   non-empty `updatedNodes` must update that same controller's
   `nodes`, and `repo.getTrip` is still called exactly once.

## 8. R17

Run each, confirm the named test fails, then restore and confirm green:

A. Remove the `listenManual` line: tests 2, 3 and 4 fail.
B. Remove the `_itinerarySub?.close()` call: test 5 fails.

## 9. Stop rules

Stop and ask if:

- step 1 does not reproduce as section 5 describes;
- the fix needs any file outside section 4;
- an existing test needs an assertion changed (an import-only change is
  also a stop here: there should be none);
- you are tempted to change `applyEvent`, the provider type, routing or
  Home;
- `ref.listenManual` is not available on the base's Riverpod version.

## 10. Gates

```
cd mobile && flutter analyze && flutter test
git diff --check
```

`flutter analyze` 0 issues, `flutter test` all passed. ASCII only in
every touched file. Do not add `SPEC-NN` references unless a spec file
with that number exists under `docs/specs/`.

## 11. Delivery

One commit on `fix/chat-controller-lifetime`:
`fix: chat holds the itinerary controller so sends are not dropped`.
Push and verify the remote SHA. Do not merge. No `gh`. No APK build or
Cloud Run deploy.

## 12. Report

1. Base SHA.
2. Branch and remote SHA.
3. Step 1 evidence: test 1 result and the exact failure lines for tests
   2 and 3 on the unmodified base.
4. `flutter analyze` and `flutter test` last lines after the fix.
5. `git diff --check` result.
6. Files touched, with +/- counts.
7. R17 A and B results.
8. Confirmation that `applyEvent`, the provider type, routing, Home and
   the itinerary screen are unchanged.
9. Anything you were unsure about.

## 13. Owner device check (after merge and APK rebuild)

Home, trip card, tap the chat bubble icon ("Ask about this trip"), open
What Now, submit with any settings. Expect a What Now result, not "I
could not complete that request". Repeat once from the itinerary's Ask
bar to confirm that path still works.
