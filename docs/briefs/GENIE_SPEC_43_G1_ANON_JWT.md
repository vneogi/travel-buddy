# Genie brief: SPEC-43 Gap 1 -- server-issued anonymous JWT

Landed on `main` as `2460edf` (PR #78). Do not re-implement this slice.
Next: `docs/briefs/GENIE_SPEC_43_G9_SIGNAL_OWNERSHIP.md` (Gaps 6 and 2 already landed).

## Goal

Stop treating a client-chosen UUID as an account credential.

The app already has `supabase_flutter` and a Bearer token provider, but
startup never signs in, so `ApiClient` falls back to
`Authorization: Anonymous <device-uuid>`. The server accepts that UUID as
`user_id` when `TB_ALLOW_ANONYMOUS=true` and no JWT secret is set. Anyone
who can guess or copy a UUID can read and mutate that identity's trips.

This slice issues a short-lived Supabase anonymous JWT, sends only
`Authorization: Bearer <access_token>`, and verifies that token from JWKS
(issuer, audience, expiry, subject, role, `kid`). The device UUID stays a
non-secret local diagnostic id. It is never an API credential.

This is SPEC-43 Gap 1 only. It is not Gap 2 (RLS), Gap 6 (sign-out wipe),
Gap 9 (signal ownership), Gap 11 (IP/spend limits), production LLM, deploy,
or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 1)
- `security.py`
- `mobile/lib/core/api_client.dart`
- `mobile/lib/core/device_identity.dart`
- `mobile/lib/core/providers.dart`
- `mobile/lib/main.dart`
- `tests/test_auth.py`
- `tests/test_anonymous_identity.py`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including uncatalogued Add `05d917e` (PR #77)
and docs `00d663a`.

Create and push:

`feat/spec43-g1-anon-jwt`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

SPEC-09 shipped a high-entropy device UUID in secure storage. That closed
"no identity at all." It did not close "the client minted the credential."
The server cannot expire it, revoke it, or tell a real device from a
replayed UUID. Unlimited new UUIDs also mint new quota rows.

Field-test Cloud Run currently relies on `TB_ALLOW_ANONYMOUS=true`. This
slice does not deploy. After a later owner deploy, that header must 401.

## Current production seams to reuse

- `security.resolve_identity` / `get_current_user_id` / `require_trip_owner`
- `config.settings` (`supabase_url`, `supabase_jwt_secret`, `jwt_audience`,
  `allow_anonymous`, `debug`)
- `PyJWT[crypto]` already in `requirements.txt`
- Flutter `Env.supabaseUrl` / `Env.supabaseAnonKey` (`TB_SUPABASE_ANON_KEY`
  is the publishable anon key, never the service-role key)
- `Supabase.initialize` in `main.dart`
- `tokenProvider` in `providers.dart`
- `DeviceIdentity` / `tbDeviceUuidKey` (keep; stop using it as Authorization)
- `tests.conftest` debug-header isolation (`TB_DEBUG=true`, JWT/URL/key
  scrubbed). Do not remove that scrubbing.

Do not add a second auth stack, a custom JWT issuer, a new user table, or
PostgREST client access from Flutter. FastAPI remains the API. Do not put
`TB_SUPABASE_KEY` (service role) in the app.

## Scope

### 1. Server verification (JWKS)

When `TB_SUPABASE_JWKS_URL` is set, Bearer tokens are verified from JWKS:

- fetch by `kid` (cache keys in process; TTL is an implementation choice)
- algorithm from the JWK, not a hardcoded HS256-only path
- require `iss` == configured issuer (`TB_SUPABASE_JWT_ISS`)
- require `aud` to include configured audience (existing `jwt_audience`,
  default `authenticated`)
- require `exp` in the future
- require `sub` non-empty (this is `user_id`)
- require `role` in `{authenticated}` (Supabase anonymous users are
  `authenticated` with `is_anonymous=true` when the claim exists)
- if `is_anonymous` is present, accept `true` or `false`; do not require
  the claim if older tokens omit it
- reject a valid token whose `iss` is another project
- rotating JWKS keys must not require an APK (server fetches JWKS)

When JWKS URL is set, do not verify production traffic with
`TB_SUPABASE_JWT_SECRET` (HS256). That secret cannot rotate without a
server config change in the way Gap 1 asks, and it is the wrong primary.

Keep the existing HS256 path only when JWKS URL is unset and
`TB_SUPABASE_JWT_SECRET` is set, so `test_debug_header_cannot_override_real_jwt`
and similar tests stay meaningful. When both are set, JWKS wins.

Identity kind for a verified Supabase JWT remains `supabase`.

### 2. Kill the Anonymous credential

`Authorization: Anonymous ...` is rejected with 401 in every configuration,
including `TB_ALLOW_ANONYMOUS=true`.

`TB_ALLOW_ANONYMOUS` becomes a no-op (keep the setting so hosted env does
not crash; log or ignore it). Update `security.py` docstring.

Pytest keeps `X-Debug-User-Id` only when `TB_DEBUG=true` and neither JWKS
URL nor JWT secret is set. That is the in-memory suite path. Debug must
never win over JWKS or JWT secret (existing regression in `test_auth.py`).

### 3. Flutter: sign in anonymously, send only Bearer

Reuse `supabase_flutter` already in `pubspec.yaml`.

After `Supabase.initialize` in `main.dart`, if there is no session, call
`signInAnonymously()`. If a session exists, reuse it (do not mint a second
account on every launch). Refresh remains the SDK default.

`ApiClient` must never send `Authorization: Anonymous ...`.

- If `tokenProvider` returns a non-empty token: `Bearer <token>`
- Otherwise: omit Authorization (the request 401s). Do not fall back to
  the device UUID.

Keep `DeviceIdentity`. It may still namespace local SQLite when no
Supabase user id exists (widget tests). Once a session exists,
`identityCacheScopeProvider` already prefers `account:<supabase user id>`.
Call anonymous sign-in before `runApp` so the first API call has a token
when `Env.supabaseUrl` and `Env.supabaseAnonKey` are set.

Do not implement Gap 6 sign-out wipe. Profile can keep navigating to
onboarding. Do not auto-merge old UUID-owned trips onto the new JWT
`sub`. Those trips stay owned by the old UUID until SPEC-24. Document
that break in the PR; it is accepted for this owner-only slice.

Widget tests that do not initialize Supabase must still run. They mock
repositories and must not call live `signInAnonymously`.

### 4. Settings

Add (names may match pydantic `TB_` env style already used):

- `TB_SUPABASE_JWKS_URL` (optional)
- `TB_SUPABASE_JWT_ISS` (optional; required when JWKS URL is set)

Do not invent a second audience setting if `jwt_audience` already exists.

Never read the service-role key in Flutter. Never log tokens, UUID
credentials, or JWKS private material.

### 5. Tests

Backend, focused file `tests/test_spec43_g1_anon_jwt.py` plus updates to
`tests/test_anonymous_identity.py` and `tests/test_auth.py`.

Use an in-process RSA (or EC) keypair and a stub JWKS. Do not call the
live Supabase Auth API in the default suite.

Must include:

- a client-selected UUID (`Authorization: Anonymous <uuid>`) cannot
  GET/POST a trip (401), including when `allow_anonymous` is True
- a well-signed JWT with the stub JWKS can `user/status` and the
  `user_id` is `sub`
- expired `exp` -> 401
- wrong `iss` -> 401
- missing `sub` or disallowed `role` -> 401
- `X-Debug-User-Id` is ignored (401) when JWKS is configured
- `X-Debug-User-Id` still works when JWKS and JWT secret are both unset
  and `TB_DEBUG=true` (existing pytest path)
- existing trip-ownership test still holds for two debug users
- zero LLM calls

Flutter, focused file `mobile/test/spec43_g1_anon_jwt_test.dart` and
update `mobile/test/api_client_test.dart`:

- with a token, the client sends `Bearer ...` and never `Anonymous`
- with a null/empty token, the client does not send `Anonymous`
- device UUID helper still round-trips in secure storage (existing
  `device_identity_test.dart` remains green)

Do not use `pumpAndSettle` or `physicalSize`. Do not hit a real network.

### 6. R17 sabotage

1. Temporarily restore the `Anonymous <uuid>` identity path in
   `resolve_identity` while JWKS is configured (accept the UUID as
   `user_id`).
2. Run the named test
   `test_anonymous_uuid_cannot_read_or_mutate_trip`.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

Report the test name that failed. A generally red file is not proof.

## Non-goals

- Gap 2 RLS / grant audit / two-JWT PostgREST isolation
- Gap 6 sign-out, token revoke denylist, identity-scoped SQLite wipe
- Gap 9 signal trip-ownership (FastAPI `require_trip_owner` already
  exists for trips; do not expand this slice into signals)
- Gap 11 IP / account-creation / spend limits (many anonymous JWTs can
  still mint many `user_tiers` rows; record that remainder)
- SPEC-24 anonymous-to-Google merge
- hosted dashboard clicks (owner must enable Anonymous sign-ins on the
  Supabase project before a later deploy; Genie does not do that here)
- hosted deploy, Cloud Run env, APK, non-owner distribution
- production LLM processing of personal trips
- new migration (no table). If a future CREATE TABLE happens later,
  grant `service_role` only -- not this slice
- fixing `postgres-proof` apt baseline
- unknown-time excursions, populated-day Add

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
flutter test test/spec43_g1_anon_jwt_test.dart test/api_client_test.dart test/device_identity_test.dart
```

R1: after any Dart write, `grep -rn '\\$' mobile/lib` must still show
only the two `upgrade_screen.dart` price strings.
