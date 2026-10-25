# Genie brief: SPEC-43 Gap 12 -- refuse another identity's trip route

Next after this lands: Gap 12 lock-screen / OS-push privacy waits until
OS push exists. Do not start Gap 5, remaining Gap 9 schema, deploy, or
an APK without a new brief.

## Goal

A `/trip/<id>` (and chat / driver-card child path) for a trip the
current identity does not own must not stay open. Redirect home.

GoRouter will build `ItineraryScreen`, `ChatScreen`, or
`DriverCardScreen` for any `tripId` in the path. Cache keys are
identity-scoped and GET `/trip/{id}` 403s a foreign owner, but the
route still opens. SPEC-43 Gap 12 acceptance: a deep link for another
user's trip is refused.

There are no custom URL schemes or VIEW intent filters. Do not add
them. Incoming here means GoRouter location: restored navigation,
`go`/`push` of a guessed id, or a future notification path of the
same shape.

This is SPEC-43 Gap 12 trip-route ownership only. HTTPS (`6f1dab8`),
cache keys (`290f821`), chat extra (`14ce56d`), and ATS (`be89128`)
are already on main. Do not re-implement them.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 12)
- `mobile/lib/routing/app_router.dart`
- `mobile/lib/routing/redirect_for_auth.dart`
- `mobile/lib/features/home/home_controller.dart` (`HomeSnapshot.trips`)
- `mobile/lib/features/home/home_screen.dart` (corridor create `go`,
  featured and list `go`)
- `mobile/lib/features/create_trip/create_trip_screen.dart` (`rangeCreate`
  then `go`)
- `mobile/lib/features/profile/sign_out_controller.dart`
- `mobile/lib/data/models.dart` (`TripSummary.tripId`, featured trip id)
- `docs/ENGINEERING_RULES.md` (R1, R14, R17)
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including ATS `be89128` (PR #92) and docs
`7177410` (PR #93).

Create and push:

`feat/spec43-g12-deeplink`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Identity B on the same install (or a pasted `/trip/<A's id>`) can
open A's itinerary route. Offline cache no longer serves A's JSON.
The screen still mounts. Refuse the route.

## Current production seams to reuse

- `redirectForAuth` -- keep it. Add a second pure redirect, or extend
  the existing file with a sibling function. Do not mix auth and
  ownership in one boolean.
- `identityCacheScopeProvider` -- do not invent a second identity
  string. The owned-id catalog is per current process identity; Gap 6
  sign-out must clear it.
- `HomeSnapshot.trips` and featured trip id -- the owned set after a
  successful or cached home snapshot.
- Create flows already `go` to the new trip. Register that id on the
  catalog **before** `go`, or the redirect will bounce a just-created
  trip home.

Do not change GET `/trip/{id}`, RLS, cache schema, chat `extra`, or
ATS XML. `?focus=` is a node id; leave it. Maps `geo:` is out of
scope.

## Scope

### 1. Pure helpers

Add one small routing file (name yours), for example
`mobile/lib/routing/trip_route_auth.dart`.

Must include:

- `tripIdFromLocation(String location)`:
  - `/trip/create` -> null
  - `/trip/<id>` -> id
  - `/trip/<id>/chat` -> id
  - `/trip/<id>/card/<nodeId>` -> id
  - ignore query strings
  - `/`, `/profile`, `/onboarding` -> null
- `redirectForTripOwnership` (name yours) with explicit catalog
  arguments, not hidden globals inside the function:
  - no trip id -> null (no redirect)
  - catalog not loaded -> null (do not block first paint / tests that
    never load home)
  - catalog loaded and id in the owned set -> null
  - catalog loaded and id missing -> `'/'`

A tiny catalog type is yours: `loaded` plus `Set<String> ids`, with
`replaceAll`, `add`, and `clear`. Tests construct it. Production may
hold one instance that `app_router` redirect reads.

### 2. Wire production

- After home snapshot (network or cache fallback), `replaceAll` trip
  ids from `trips` and featured if present.
- Corridor create on home and range create on create-trip: `add` the
  new `trip.tripId` before `context.go`.
- Gap 6 sign-out: `clear` the catalog.
- Successful itinerary `getTrip`: `add` that trip id (covers a trip
  that home has not listed yet).
- `app_router` `redirect`: after `redirectForAuth`, if that returns
  null, run `redirectForTripOwnership` on `state.matchedLocation` or
  `state.uri.path`.

Do not mount new screens. Do not add Android intent-filters or iOS
URL types.

### 3. Tests

New file `mobile/test/spec43_g12_deeplink_test.dart`.

No widgets, no `pumpAndSettle`, no `physicalSize`, no SQLite, no
network. Pure functions only.

Named test that must exist with this exact name:

`test_foreign_trip_deep_link_is_refused`

It must:

1. Build a loaded catalog that contains `trip-owned` only.
2. Call the production redirect helper with location
   `/trip/trip-foreign`.
3. Expect `'/'`.
4. Also assert `/trip/trip-foreign/chat` and
   `/trip/trip-foreign/card/node-1` redirect to `'/'`.

Add further tests (names yours):

- owned `/trip/trip-owned` (and chat / card) -> null
- `/trip/create` -> null
- catalog not loaded + `/trip/trip-foreign` -> null
- `tripIdFromLocation('/trip/create')` is null

Do not add widget tests of ItineraryScreen for this slice.

## Out of scope

- Custom schemes, App Links, universal links, VIEW intent-filters
- Lock-screen notification text
- SQLCipher, RLS apply, Gap 1 Cloud Run deploy, APK
- Changing `assertSecureTransport`, cache PKs, or chat extra
- Hardcoding USD prices (R1)

## R17 sabotage (owner laptop, after your report)

Exact edit, not a one-word swap:

In the production `redirectForTripOwnership` (or equivalent), make the
foreign-id branch return `null` instead of `'/'` (always allow).

`test_foreign_trip_deep_link_is_refused` must fail because `/trip/trip-foreign`
is no longer redirected home. A test that only checks
`tripIdFromLocation` is the wrong test.

Restore before the PR. Do not sabotage by deleting the test.

## Gates

From repo root, with `backend/.venv` and `mobile/`:

```
backend/.venv/bin/python -m pytest tests/ -q --tb=short
cd mobile && flutter analyze && flutter test
```

If `backend/.venv` is missing, `python3 -m pytest tests/ -q --tb=short`
from the repo root. Paste the last pytest counts line, `flutter analyze`
(0 errors; infos may already exist), and `flutter test` All tests
passed. Owner then runs R17 and the same Flutter commands on Windows.

## Report

SHA, branch, pytest last line, analyze, flutter test, files touched,
and the helper names. Do not merge. Do not edit this brief,
PROJECT_STATUS, or HANDOFF.

R1: `rg '\$' mobile/lib --glob '*.dart'` must not gain a price.
Path interpolation `$tripId` is not a dollar amount. Do not add `$29`.
