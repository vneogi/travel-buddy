# Genie brief: SPEC-43 Gap 12 -- chat question out of route URLs

Landed on `main` as `14ce56d` (PR #89). Do not re-implement this slice.
ATS `be89128`. Deep-link ownership `f486079`. Gap 9 schemas
`fb72545`. Next: `docs/briefs/GENIE_SPEC_43_G9_RANKING_ISOLATION.md`.

## Goal

Ask text must not appear in the GoRouter location, browser-style
history, restored navigation, or any `?q=` query string.

Today itinerary Ask encodes the question into
`/trip/:tripId/chat?q=...`. ChatScreen seeds from
`state.uri.queryParameters['q']`. That is the Gap 12 navigation leak
for chat.

This is SPEC-43 Gap 12 chat URLs only. HTTPS fail-closed (`6f1dab8`)
and identity-scoped caches (`290f821`) are already on main. Do not
re-implement them. This is not Android network-security XML, iOS ATS,
custom URL schemes, Gap 5 SQLCipher, Gap 9 schema, deploy, or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 12)
- `mobile/lib/routing/app_router.dart` (`/trip/:tripId/chat`)
- `mobile/lib/features/itinerary/itinerary_screen.dart` (AskEntryBar
  `onSubmit` at the `?q=` push)
- `mobile/lib/features/home/home_screen.dart` (chat push with no `q`;
  keep that shape)
- `mobile/lib/features/chat/chat_screen.dart` (`initialQuestion`)
- `docs/ENGINEERING_RULES.md` (R1, R14, R17)
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including Gap 12 cache `290f821` (PR #85)
and docs `86d38ab` (PR #87).

Create and push:

`feat/spec43-g12-chat-url`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

SPEC-43 Gap 12 acceptance includes: route logs and restored
navigation contain no question text. Query strings are logged, shared,
and restored. `extra` is not part of the URI. Put the question in
`GoRouter` `extra` only.

Do not read `q` from the URI even if an old deep link still has it.
Fail closed: ignore query `q`. Chat opens empty rather than seeding
from the URL.

## Current production seams to reuse

- `ChatScreen.initialQuestion` -- keep the constructor. Change only
  how the router supplies it.
- Itinerary `AskEntryBar.onSubmit` -- the only production writer of
  `?q=`.
- Home chat push `/trip/${trip.tripId}/chat` -- no question; leave
  the path, do not add a query.
- History thread open already constructs `ChatScreen(threadId: ...)`
  in-widget. Do not put thread ids or message text into the URI.

Do not change Ask persistence, `/trip/event`, identity cache keys, or
HTTPS. `geo:` / maps `q=` in driver-card helpers is maps search, not
this route. Leave it.

`/trip/:tripId?focus=` is a node id, not Ask text. Leave it.

## Scope

### 1. Typed extra, not query string

Add a small typed extra (name is yours) used only for this route,
for example `ChatRouteExtra` with `String? initialQuestion`.

Production location for chat is exactly `/trip/<tripId>/chat` with
no query string.

Itinerary Ask must `context.push` that location and pass
`extra: ChatRouteExtra(initialQuestion: question)`.

Router builder:

- `tripId` from `state.pathParameters['tripId']`
- `initialQuestion` from typed `extra` only
- never `state.uri.queryParameters['q']`

If `extra` is missing or the wrong type, `initialQuestion` is null.

Put the path helper and extra type in one small routing file so
itinerary, tests, and the router share them. Do not duplicate the
path string with a `?q=` variant.

### 2. Tests

New file `mobile/test/spec43_g12_chat_url_test.dart`.

Do not mount `ChatScreen`, `ItineraryScreen`, SQLite, or Riverpod
overrides. Use a tiny `GoRouter` whose chat `builder` records
`state.uri` and `state.extra` and returns `const SizedBox()`.

No `pumpAndSettle`. No `tester.view.physicalSize`. `tester.pump()`
after `push` is enough.

Named test that must exist with this exact name:

`test_chat_question_is_not_in_route_uri`

It must:

1. Use the same production path helper and extra type as itinerary.
2. `push` with a distinctive question string that is not a trip id
   (example: `secret ask about hidden courtyard`).
3. Assert the recorded URI path is `/trip/<tripId>/chat`.
4. Assert the URI has no query (`queryParameters` empty, or at least
   no `q`).
5. Assert the URI string does not contain the question text (raw or
   percent-encoded).
6. Assert typed extra still carries that question.

Add a second test (name is yours) that `go`s
`/trip/<tripId>/chat?q=<question>` with no extra and asserts
`initialQuestion` from extra is null / extra is not that question.
The router must not recover the question from `q`.

Do not add widget tests of AskEntryBar. Do not screenshot.

## Out of scope

- Android `network_security_config.xml` / iOS ATS
- Custom URL schemes and deep-link ownership
- SQLCipher, RLS apply, Gap 1 Cloud Run deploy, APK
- Changing `ChatScreen` send/persist behavior once
  `initialQuestion` is supplied
- Putting Ask text into logs, analytics, or crash keys
- Hardcoding USD prices (R1)

## R17 sabotage (owner laptop, after your report)

Exact edit, not a one-word swap:

In the production itinerary Ask `onSubmit` (or the shared helper it
calls), restore a query string:

`'/trip/$tripId/chat?q=${Uri.encodeQueryComponent(question)}'`

and drop `extra` (or keep extra; URI leak is enough).

`test_chat_question_is_not_in_route_uri` must fail because the
recorded URI contains the question. A test that only checks extra
and ignores the URI is the wrong test.

Restore the extra-only push before the PR.

Do not sabotage by deleting the test.

## Gates

From repo root, with `backend/.venv` and `mobile/`:

```
backend/.venv/bin/python -m pytest tests/ -q --tb=short
cd mobile && flutter analyze && flutter test
```

Paste the last pytest counts line, `flutter analyze` (0 issues), and
`flutter test` All tests passed. Owner then runs R17 and the same
Flutter commands on Windows.

## Report

SHA, branch, pytest last line, analyze, flutter test, files touched,
and the exact extra type plus path helper names. Do not merge.
Do not edit this brief, PROJECT_STATUS, or HANDOFF.

R1: `rg '\$' mobile/lib --glob '*.dart'` must not gain a price. Chat
paths use `$tripId` interpolation; that is not a dollar amount.
Do not add `$29`.
