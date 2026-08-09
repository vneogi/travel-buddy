# SPEC-09: Anonymous Device Identity

## Goal

Replace the `--dart-define=TB_DEBUG_USER_ID` hardcoded UUID with a per-device
identity generated on first launch. No screens, no PII, no login.

## Why this is blocking

1. `TB_DEBUG_USER_ID` is a build-time constant — all testers share one user id
2. It only works because `TB_DEBUG=true` — ship with false and no identity
3. It's a dev-mode header — production dependent on a debug path

## Design

Generate UUID v4 on first launch. Persist in flutter_secure_storage. Send as:

```
Authorization: Anonymous <device-uuid>
```

Server-side resolution order (security.py):
1. Real Supabase JWT (when jwt_secret set) → verified user
2. `Authorization: Anonymous <uuid>` → validate UUID v4, use as user_id
3. `X-Debug-User-Id` → only when no JWT secret AND debug=true
4. Otherwise 401

## Guards

- Reject anything that isn't a valid UUID v4
- `Anonymous` rejected when JWT secret configured (TB_ALLOW_ANONYMOUS flag)
- Regression test for both

## Server: no schema change needed

user_tiers.user_id is already uuid. get_or_create_user creates free-tier on first
sight. One addition: `identity_kind` column (anonymous/supabase) on user_tiers.
Migration 0009.

## Client changes

- `mobile/lib/core/device_identity.dart` — getOrCreate(), memoized
- `mobile/lib/core/api_client.dart` — send Anonymous header
- `mobile/lib/core/env.dart` — drop TB_DEBUG_USER_ID
- main.dart resolves id before runApp
- scripts/start-app.ps1 — remove TB_DEBUG_USER_ID dart-define

## Tests

- First launch generates v4; second returns same
- getOrCreate() safe to call concurrently
- ApiClient sends Anonymous header
- Server: valid UUID → 200; malformed → 401; non-v4 → 401
- Server: Anonymous rejected when JWT secret configured

## Acceptance

- [ ] No TB_DEBUG_USER_ID in mobile/lib or scripts/
- [ ] Identity resolved before runApp
- [ ] Server validates UUID v4; malformed → 401
- [ ] Anonymous disabled when JWT secret present, with test
- [ ] identity_kind on user_tiers (migration 0009)
- [ ] Device id visible on profile
- [ ] Suite green (R8); verified from origin/main (R10)
