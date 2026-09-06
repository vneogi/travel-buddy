# Genie Brief: SPEC-37 Phone-Independent Field-Test Delivery

> Status: READY. SPEC-36 is merged to `origin/main` at `1f2c43d` (PR #55).
> Do not start from `feat/spec36-laos-corridor`. Deploy only reviewed `main`.
> New branch: `feat/spec37-phone-field-test` from `origin/main` at `1f2c43d`.

## Read first

- `docs/specs/SPEC-37-phone-field-test-delivery.md` (authoritative)
- `docs/TESTING_GUIDE.md` section 6
- `docs/HOSTED_STATE.md`
- `docs/ENGINEERING_RULES.md` R7, R11
- This brief

Target owner acceptance: 2026-09-18.

## Mission

A field-test build that runs on the owner's phone with the laptop gone:

1. reviewed `main` (`1f2c43d` or later on `main`) deployed to stable HTTPS;
2. backend-only secrets on that hosted service;
3. an installable artifact compiled against that URL;
4. owner proves the Laos corridor online;
5. owner proves cached itinerary and driver cards in airplane mode with
   USB and local tunnels disconnected.

## Preflight hard stops

Stop and report; do not guess:

1. `git fetch origin && git rev-parse origin/main` is not an ancestor of or
   equal to current `main` containing `1f2c43d`.
2. The owner has not named **Android** or **iOS**. Ask once, then wait.
3. The owner has not confirmed the leaked Google Maps key was rotated.
   Do not install the old key on the hosted service.
4. You do not have a container target the owner can actually provision
   (Railway if they have `RAILWAY_TOKEN` and a service; otherwise one
   supported container, no app redesign).

Never request secret values in chat. The owner enters them in the host
and signing consoles.

## Phase A: hosted backend

Required hosted configuration (values never appear in the repo or PR):

```text
TB_DEBUG=false
TB_ALLOW_ANONYMOUS=true
TB_SUPABASE_URL=<hosted secret>
TB_SUPABASE_KEY=<hosted service-role secret>
TB_LITELLM_API_KEY=<hosted secret>
TB_GOOGLE_MAPS_API_KEY=<rotated hosted secret>
TB_OPENWEATHER_API_KEY=<hosted secret>
```

Keep `TB_SUPABASE_JWT_SECRET` unset. Laptop `.env` is not deployment
config. Do not put service-role, LLM, Maps, or Weather keys in Flutter.

Proof Genie can produce without the phone:

- HTTPS `GET /api/v1/health` succeeds from a non-laptop network;
- startup logs booleans only (`llm_key_present`, `supabase_configured`,
  `jwt_auth`); never values;
- `TB_DEBUG` is false;
- Anonymous `GET /api/v1/trips` and trip read succeed;
- `GET /api/v1/trip/{id}/notifications` is not `unconfigured`.

## Phase B: installable artifact

`ApiClient` appends `/api/v1`. Compile with the host root only:

```text
--dart-define=TB_API_BASE_URL=https://<hosted-api>
```

Android: signed release APK for sideload. iOS: TestFlight with the owner's
Apple signing. No emulator substitute. No `flutter run` as the delivery.

Record in the PR (no secrets): source commit, platform, artifact type,
hosted API hostname, secret-free build command.

## Phase C: owner acceptance

Genie prepares checklist only. The owner records online and airplane-mode
results in `docs/AWAITING_VERIFICATION.md`. Invalid if the app uses
`flutter run`, localhost, `10.0.2.2`, laptop LAN, USB networking, or
`adb reverse` (R7).

## Non-goals

- No new consumer feature, OS push, background GPS, offline map tiles,
  public store, or SPEC-24 identity merge.
- No SPEC-36 itinerary changes.
- No SPEC-29 Heads-up / interruption-budget work on this branch.
- No new deployment framework if the current container works.

## Gates

```bash
git fetch origin
git checkout -b feat/spec37-phone-field-test origin/main
pytest -q -ra
ruff check .
```

From `mobile/` if Flutter is available:

```bash
flutter analyze --no-fatal-infos
flutter test
```

If Flutter is unavailable, say so. Report skips with reasons (R8).

## Completion

1. Open a focused PR into `main`. Do not merge.
2. Report SHA, compare URL, checks, and what the owner must still enter
   (platform, rotated Maps key, host secrets, signing).
3. Do not claim hosted or phone acceptance without owner evidence.
4. After owner acceptance, update `docs/HOSTED_STATE.md` and a dated
   finding in `docs/AWAITING_VERIFICATION.md`.
