# Genie Brief: SPEC-37 Phone-Independent Field-Test Delivery

> Status: QUEUED AFTER SPEC-36 MERGES. Do not start from the SPEC-36 feature
> branch and do not deploy an unreviewed commit.

## Read first

- `docs/specs/SPEC-37-phone-field-test-delivery.md`
- `docs/PROJECT_STATUS.md`
- `docs/HOSTED_STATE.md`
- `docs/TESTING_GUIDE.md`, especially section 6
- `docs/ENGINEERING_RULES.md`, especially R7

The target acceptance date is 2026-09-18, about two weeks before travel.

## Mission

Produce a field-test build that runs on the owner's phone without the laptop:

1. reviewed `main` is deployed to a stable HTTPS backend;
2. backend-only credentials are configured on that hosted service;
3. an installable phone artifact is compiled against that URL;
4. the owner proves the corridor online; and
5. the owner proves cached itinerary and driver cards in airplane mode with
   USB and local tunnels disconnected.

## Preflight hard stops

Stop before changing deployment or build configuration unless:

- SPEC-36 is merged to `origin/main`;
- backend CI and Flutter gates are green on that merged SHA;
- the owner names the target phone platform;
- the owner has access to the chosen hosting and signing accounts; and
- the exposed Google Maps key has been rotated and restricted.

Never request secret values in chat. The owner enters them directly in the
hosting or signing service.

## Phase A: hosted backend

Use the existing container and CI path. Prefer the prepared Railway route if
the owner provisions its service, `RAILWAY_TOKEN`, and `PRODUCTION_URL`;
otherwise use another supported container target without redesigning the app.

Required hosted configuration:

```text
TB_DEBUG=false
TB_ALLOW_ANONYMOUS=true
TB_SUPABASE_URL=<hosted secret>
TB_SUPABASE_KEY=<hosted service-role secret>
TB_LITELLM_API_KEY=<hosted secret>
TB_GOOGLE_MAPS_API_KEY=<rotated hosted secret>
TB_OPENWEATHER_API_KEY=<hosted secret>
```

Keep `TB_SUPABASE_JWT_SECRET` unset for the Anonymous field-test path. Do not
put the service-role, LLM, Maps, or Weather keys in Flutter.

Proof:

- HTTPS health succeeds from outside the laptop network;
- startup reports credential presence only, never values;
- `TB_DEBUG` is false;
- an Anonymous device can list and read its trip; and
- provider-backed notification retrieval is not `unconfigured`.

## Phase B: installable artifact

`ApiClient` appends `/api/v1`; compile with the host root:

```text
--dart-define=TB_API_BASE_URL=https://<hosted-api>
```

For Android, produce a signed release APK suitable for direct installation.
For iOS, use TestFlight and the owner's Apple signing setup. Do not silently
substitute an emulator build.

Record:

- source commit;
- platform and device;
- artifact type;
- hosted API hostname, without query strings or credentials; and
- build command with secret-free defines only.

## Phase C: owner acceptance

The owner performs and records the SPEC-37 online and offline acceptance.
Genie may prepare scripts or checklists but cannot claim device evidence.

The offline run is invalid if the app uses `flutter run`, localhost,
`10.0.2.2`, a laptop LAN address, USB networking, or `adb reverse`.

## Non-goals

- No new consumer feature.
- No OS push, background GPS, real offline maps, or public store launch.
- No identity merge.
- No SPEC-36 fixes on this branch.
- No new deployment framework if the current container works.

## Completion

1. Open a focused PR for any repository changes.
2. Report backend, Flutter, and build checks with skip reasons.
3. Do not merge the PR.
4. Do not claim hosted or phone acceptance without owner evidence.
5. After owner acceptance, update `docs/HOSTED_STATE.md` and the dated finding
   in `docs/AWAITING_VERIFICATION.md`.
