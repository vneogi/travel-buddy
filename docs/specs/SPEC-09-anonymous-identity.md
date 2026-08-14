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

## Amendments before implementation

Four things were wrong or unstated here, found while briefing the work.

**The migration number is stale.** This said migration 0009, which has since been
taken by venue_dish cuisine and pricing. Migration numbers are claimed at
implementation time, never in a spec; that is a recorded process defect from an
earlier collision.

**`Authorization: Anonymous <uuid>` will not reach the handler as written.** The
server uses FastAPI's `HTTPBearer`, which parses only the `Bearer` scheme and
rejects everything else before any code here runs. Read the raw `Authorization`
header and parse the scheme explicitly. Do not loosen the bearer check to make
this work, because that weakens the verified-JWT path to fix the anonymous one.

**`TB_ALLOW_ANONYMOUS` defaults to false.** The spec named the flag without a
default. It fails closed, matching `debug: bool = False` and its comment that
production never trusts debug headers by default. An anonymous identity has to be
switched on deliberately for a tester build.

**Rejecting non-v4 has a privacy reason, not only a hygiene one.** A v1 UUID
embeds the generating device's MAC address and a timestamp, so accepting one
would put a hardware identifier in every request from an app whose whole claim is
that it holds no PII. Validate the version and variant bits, not merely that the
string parses.

**Known limitation, to be recorded rather than solved here.** An anonymous UUID in
a header is an unverified bearer secret: anyone who learns it can impersonate that
device. That is acceptable for a tester build carrying no PII and unacceptable the
moment real accounts exist, which is what the JWT path is for. Say so in the code
comment, so the next reader does not mistake this for authentication.

## Sequencing: the server half is not blocked, the client half is

The Python side, including the migration and every server test, can be built and
verified now. The Flutter side cannot be verified by anyone until the SDK is
installed, since this repo has never been compiled. Build the server half first
and leave the client half to follow; the acceptance list is not met until both
land.

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
- [ ] identity_kind on user_tiers (migration number taken at implementation time)
- [ ] Anonymous scheme parsed from the raw Authorization header, with the bearer
      path unchanged
- [ ] TB_ALLOW_ANONYMOUS defaults to false, with a test that anonymous fails when
      the flag is unset
- [ ] UUID version and variant bits validated, with a test that a v1 UUID is
      rejected
- [ ] Device id visible on profile
- [ ] Suite green (R8); verified from origin/main (R10)
