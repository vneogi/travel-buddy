# Genie brief: SPEC-43 Gap 6 -- sign-out as identity lifecycle

## Goal

Make Profile "Sign Out" a real identity change, not a navigation.

Today the button only `context.go('/onboarding')`. The Supabase session,
sync engine, outbox, and SQLite caches stay on disk. After Gap 1 the
session is a real JWT, so that leftover is now an account, not a
device UUID.

Sign-out must: stop sync, discard the prior identity's local rows
(including outbox -- never upload them under a new token), clear the
provider session, then mint a *new* anonymous JWT only after the prior
account is inaccessible. Home then shows an empty vault for the new
identity. Account A's trips, Ask threads, hearts, alerts, and queued
signals must not appear for account B.

This is SPEC-43 Gap 6 only. It is not Gap 2 (RLS), Gap 5 (SQLCipher),
Gap 9 (signal ownership), account deletion, SPEC-24 merge, deploy, or
an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 6)
- `docs/briefs/GENIE_SPEC_43_G1_ANON_JWT.md`
- `mobile/lib/features/profile/profile_screen.dart`
- `mobile/lib/core/anon_session.dart`
- `mobile/lib/core/providers.dart` (`identityCacheScopeProvider`)
- `mobile/lib/offline/offline_database.dart`
- `mobile/lib/offline/sync_engine.dart`
- `mobile/lib/routing/redirect_for_auth.dart`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including Gap 1 `2460edf` (PR #78).

Create and push:

`feat/spec43-g6-signout`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 1 made `signInAnonymously()` the account. Sign-out still pretends
the account is a screen. A shared phone, a leftover outbox, or a
router bounce would keep serving A's itinerary under B's Bearer.

## Current production seams to reuse

- `ensureAnonymousSession` / `AnonAuth` / `SupabaseAnonAuth`
- `Supabase.instance.client.auth.signOut()`
- `SyncEngine.stop`, `authHalted`, `resetAuthHalted`
- `OfflineDatabase` tables: `outbox`, `cache_trip`, `cache_place`,
  `cache_trip_list`, `alert_cache`, `alert_dismissals`, `loved_places`,
  `app_kv`, `node_outcome`, `ask_thread`, `ask_message`,
  `notification_cache`, `notification_dismissals`
- `identityCacheScopeProvider` (`account:<sub>` vs `anonymous:<device>`)
- `DeviceIdentity` (local diagnostic; not an API credential)
- Profile Sign Out button (danger-colored TextButton)

Do not add a server token denylist, a new table, or a Flutter command
outbox. Do not encrypt SQLite (Gap 5). Do not call the service-role
key from the app.

## Scope

### 1. Ordered sign-out

One function (name is yours) owned by the client, called from Profile.
Order is required:

1. Halt sync so no in-flight POST continues (`stop` and/or set
   `_authHalted`; do not `resetAuthHalted` until the new identity exists).
2. Delete the prior identity's local rows, **including the entire
   outbox**. Do not sync-then-delete. A queued signal from A must never
   POST with B's Bearer.
3. `signOut()` the GoTrue session (clears access and refresh locally;
   SDK revoke is enough -- no new revoke API).
4. Confirm `currentSession` is null.
5. Only then `ensureAnonymousSession` so a *new* anonymous JWT exists.
6. Reset auth-halted, restart sync for the new identity.
7. Invalidate identity-scoped Riverpod providers (user status, home,
   itinerary, alerts, notifications, Ask thread).
8. Navigate to `/` (empty home for the new identity). Do not keep the
   user inside `/trip/<old-id>`.

If step 5 fails, stay signed out (no Bearer, API 401) rather than
restoring A's session. Surface a short existing-style error; do not
crash.

Keep the device UUID in secure storage. It is not the account. Do not
write it as `Authorization`.

### 2. Local wipe

Add one `OfflineDatabase` method that deletes every row in the tables
listed above. Identity-scoped tables and unscoped caches both go: an
unscoped `cache_trip` still holds A's itinerary.

Do not drop the database file. Do not recreate schema. `DELETE FROM`
each table, then vacuum is optional and not required.

Ask threads, loved hearts, node outcomes, alert/notification
dismissals, and `app_kv` (including `last_session_at`) are in scope.
After wipe, a cold `session_start` for B is a first open.

### 3. Router

`redirectForAuth` must not bounce a just-signed-out user back into A's
session. After step 5 a new session exists, so sending them to `/` is
correct. Do not require the onboarding carousel for sign-out.

If they land on `/onboarding` with a new session, the existing
"authenticated + onboarding -> `/`" redirect is fine.

### 4. Profile UI

Replace the TODO. The button stays visible and keyed
(`profile_sign_out`). Disable it while the sequence runs. Do not ask
for a password (there is none on anonymous JWT). Account deletion and
"reauthenticate for destructive delete" are out of this slice.

### 5. Tests

Focused Flutter file `mobile/test/spec43_g6_signout_test.dart`.

Use unique in-memory `OfflineDatabase(testPath:)`, a fake `AnonAuth`,
and a fake/controlled `SyncEngine` or the real engine pointed at the
test db. No live Supabase. No `pumpAndSettle`. No `physicalSize`.

Must include:

- sign-out calls `signOut` then exactly one `signInAnonymously` for a
  *new* session (prior `hasSession` was true)
- after wipe, `cache_trip` / `cache_trip_list` / `outbox` /
  `ask_thread` / `loved_places` / `node_outcome` are empty
- outbox rows queued under A are gone before the new Bearer exists
  (capture token provider across the sequence; no POST uses A's
  leftover rows with B's token)
- home/itinerary providers after sign-out do not still hold A's nodes
- router: signed-out user is not left on `/trip/<A's id>`
- Gap 1 regressions: `spec43_g1_anon_jwt_test.dart` and
  `api_client_test.dart` still never send `Anonymous`

Backend: no new Python endpoint required. Do not add pytest unless you
touch Python (you should not).

### 6. R17 sabotage

1. Temporarily skip deleting `outbox` during sign-out (leave A's
   pending rows, then mint B and allow sync).
2. Run the named test
   `test_sign_out_does_not_upload_prior_outbox_under_new_identity`.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

Report the test name that failed. A generally red file is not proof.

## Non-goals

- Gap 2 RLS / PostgREST isolation
- Gap 5 encrypted vault / Android backup exclusions
- Gap 9 signal trip-ownership on the server
- Gap 11 IP / account-creation limits
- server-side access-token denylist (access tokens may live until
  `exp`; refresh is cleared by `signOut`)
- SPEC-24 Google/Apple link and history merge
- account deletion / export
- rotating the device UUID
- hosted deploy, Cloud Run env, APK
- production LLM
- fixing `postgres-proof` apt baseline

## Gates

```bash
ruff check .
ruff format --check .
pytest -q -ra --strict-markers
git diff --check
```

Flutter (say so if the SDK is absent; do not claim it green):

```bash
flutter analyze --no-fatal-infos
flutter test test/spec43_g6_signout_test.dart
flutter test test/spec43_g1_anon_jwt_test.dart test/api_client_test.dart test/device_identity_test.dart
```

R1: after any Dart write, `grep -rn '\\$' mobile/lib` must still show
only the two `upgrade_screen.dart` price strings.
