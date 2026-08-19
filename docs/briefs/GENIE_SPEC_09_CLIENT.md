# Genie Brief -- SPEC-09 Client Half (Anonymous Device Identity)

> Status: READY TO IMPLEMENT. Paste this entire file to Genie Code.
> Land via PR to main, not direct push. Owner has no laptop this week --
> write unit tests that do not need a device; device acceptance stays open.

Canonical spec: `docs/specs/SPEC-09-anonymous-identity.md`
Server half: DONE (security.py, migration 0018, tests/test_anonymous_identity.py).
Do not rework the server. This brief is Flutter only plus script/README cleanup.

## Goal

Replace `--dart-define=TB_DEBUG_USER_ID` with a per-device UUID v4 generated
on first launch, persisted in secure storage, sent as:

```
Authorization: Anonymous <device-uuid>
```

No screens beyond showing the id on Profile. No PII. No login. No SPEC-24.

## Why this is next

October spine item 2. Without it every tester shares one debug user and
production with `TB_DEBUG=false` has no identity. Server already accepts
Anonymous when `TB_ALLOW_ANONYMOUS=true`.

## Current code (change these)

| Path | Today |
|---|---|
| `mobile/lib/core/env.dart` | `debugUserId` / `TB_DEBUG_USER_ID` |
| `mobile/lib/core/api_client.dart` | Bearer token, else `X-Debug-User-Id` |
| `mobile/lib/core/providers.dart` | ApiClient(tokenProvider) only; comment mentions debug header |
| `mobile/lib/main.dart` | No identity resolve before runApp |
| `mobile/lib/features/profile/profile_screen.dart` | No device id |
| `mobile/pubspec.yaml` | Has `uuid`; **no** `flutter_secure_storage` |
| `mobile/README.md` | Documents TB_DEBUG_USER_ID |
| `scripts/start-app.ps1` | Passes TB_DEBUG_USER_ID dart-define -- remove |
| `scripts/dev.ps1` | Passes TB_DEBUG_USER_ID -- remove those defines |

There is no `mobile/lib/core/device_identity.dart` yet. Create it.

## Design rules (do not invent alternatives)

1. **Storage:** `flutter_secure_storage` only for the device UUID. Key name:
   `tb_device_uuid` (constant in device_identity.dart).
2. **Format:** UUID v4, canonical lowercase hex with hyphens
   (`xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`). Generate with package `uuid`.
3. **Memoization:** `DeviceIdentity.getOrCreate()` must be safe under
   concurrent callers (single in-flight Future / lock). Second call returns
   the same string without writing again.
4. **Header precedence in ApiClient:**
   - If Supabase access token present -> `Authorization: Bearer <jwt>`
   - Else -> `Authorization: Anonymous <device-uuid>`
   - **Remove** `X-Debug-User-Id` / `TB_DEBUG_USER_ID` from mobile/lib and
     scripts. Do not keep a fallback to the debug header in the client.
5. **Lifecycle:** Resolve identity in `main()` after
   `WidgetsFlutterBinding.ensureInitialized()` and before `runApp` (and
   before starting SyncEngine, so the first sync already carries Anonymous).
6. **Profile:** Show a truncated or full device id (read-only text). Label it
   clearly as device id, not account. No copy-to-clipboard required unless
   trivial.
7. **Riverpod:** Prefer a `deviceIdentityProvider` (FutureProvider or
   Provider after eager resolve) so Profile and ApiClient share one source.
   ApiClient constructor may take `Future<String> Function() deviceId` or
   the resolved String after main() eagerly awaits getOrCreate -- pick one
   pattern and keep it simple. Do not leave ApiClient reading Env.debugUserId.

## Server / env note (document in PR, do not change Python)

Local or tester API must run with:

```
TB_ALLOW_ANONYMOUS=true
```

and without a JWT secret forcing Anonymous off (see security.py). Default
remains fail-closed. README should say: client sends Anonymous; backend must
opt in. Do not flip the server default to true.

## Implementation checklist

1. Add `flutter_secure_storage` to `mobile/pubspec.yaml` (current stable).
2. Create `mobile/lib/core/device_identity.dart` with `getOrCreate()`.
3. Wire `main.dart`: await getOrCreate before syncEngine.start / runApp.
4. Update `ApiClient` + `providers.dart` for Anonymous header; delete debug
   user path from `env.dart`.
5. Profile: display device id.
6. Remove TB_DEBUG_USER_ID from `mobile/README.md`, `scripts/start-app.ps1`,
   and any other scripts under `scripts/` or `mobile/`.
7. Grep the repo: no remaining `TB_DEBUG_USER_ID` under `mobile/` or
   start-app scripts (docs/specs mentioning it historically are fine).

## Tests (must land with the PR; no device required)

Add `mobile/test/device_identity_test.dart` (and ApiClient test as needed):

1. **First launch generates v4** -- inject a fake store (in-memory map) so
   tests do not need the plugin. Assert version nibble is 4 and variant bits
   are RFC 4122.
2. **Second call returns same id** -- same fake store; no second write of a
   different value.
3. **Concurrent getOrCreate** -- kick off several Futures; all complete with
   identical id; only one generate path.
4. **ApiClient sends Anonymous header** when tokenProvider returns null --
   use Dio interceptor mock or mock adapter; assert
   `Authorization` is exactly `Anonymous <uuid>` (scheme case as implemented;
   server parses case-insensitively but client should send `Anonymous`).
5. **ApiClient prefers Bearer** when tokenProvider returns a token -- no
   Anonymous header on that request.

Sabotage before trusting (R17): break the memoization so two UUIDs can be
minted and confirm test 2 or 3 fails by name.

Do not claim `flutter analyze` / device acceptance passed unless CI or the
owner ran them. Unit tests in `mobile/test/` are the bar for this PR.

## Out of scope

- SPEC-24 sign-in / merge
- SPEC-22 / SPEC-12 / SPEC-10 / SPEC-04
- Changing security.py, TB_ALLOW_ANONYMOUS default, or migration 0018
- Re-enabling Google Maps / RevenueCat
- Rewriting Profile UI beyond showing the device id
- Direct commits to main

## PR

- Branch: `feat/spec-09-client-anonymous-identity` (or similar)
- Title: `feat(mobile): SPEC-09 anonymous device identity (client half)`
- Body: summary, test plan (unit tests listed), note that device acceptance
  and `TB_ALLOW_ANONYMOUS=true` backend check await owner laptop
- Open PR against `main`. Do not squash-merge yourself unless asked.

## Acceptance (from SPEC-09; mark in PR)

Client-owned (this PR):

- [ ] No TB_DEBUG_USER_ID in mobile/lib or scripts/
- [ ] Identity resolved before runApp
- [ ] Device id visible on profile
- [ ] Unit tests above green

Already true on server (do not re-verify as new work):

- [x] Server UUID v4 validation / Anonymous parsing / fail-closed flag /
      identity_kind

Owner laptop later:

- [ ] End-to-end against API with TB_ALLOW_ANONYMOUS=true
- [ ] flutter analyze && flutter test on device/CI if not in this PR's CI
