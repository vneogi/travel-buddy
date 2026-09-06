# SPEC-37: Phone-Independent Field-Test Delivery

> Status: SPECIFIED, NOT IMPLEMENTED.
>
> Starts only after SPEC-36 is merged and green. This is a delivery and
> acceptance slice, not a new consumer feature.
>
> Target final online and airplane-mode acceptance: 2026-09-18, approximately
> two weeks before the 2026-10-02 trip.
>
> Execution brief: `docs/briefs/GENIE_SPEC_37_PHONE_FIELD_TEST.md`.

## Goal

Put the real Laos trip on the owner's phone in a form that works away from the
laptop. The acceptance build uses a stable HTTPS backend, can be launched
without `flutter run`, and retains the itinerary and driver-card essentials
when the phone loses connectivity.

Success is not an emulator screenshot or a phone connected through USB. The
owner must be able to leave the laptop behind.

## Scope

### 1. Hosted backend

- Choose and provision one supported container target.
- Deploy the image produced from reviewed `main`.
- Set `TB_DEBUG=false`.
- Rotate the previously exposed Google Maps key before installing it on the
  hosted service; retain API and application restrictions.
- Set hosted Supabase URL and service-role key.
- Set the LLM key required by existing intelligent paths.
- Set `TB_GOOGLE_MAPS_API_KEY` and `TB_OPENWEATHER_API_KEY`.
- Set `TB_ALLOW_ANONYMOUS=true` until the account flow replaces device
  identity.
- Expose a stable HTTPS base URL and configure the deployment health check.
- Never put the Supabase service-role key or provider keys in Flutter.

The local Windows `.env` is not deployment configuration. Provider smoke tests
recorded in `docs/HOSTED_STATE.md` prove only the laptop process until the
hosted endpoint is tested.

### 2. Installable phone build

Compile the reviewed client with:

```text
TB_API_BASE_URL=https://<hosted-api>
```

Use the delivery path appropriate to the owner's phone:

- Android: signed installable APK for direct field testing; or
- iOS: TestFlight build with the required Apple signing and review setup.

The artifact must launch from the phone home screen after disconnecting the
development cable. `flutter run`, localhost, `10.0.2.2`, laptop LAN addresses,
and `adb reverse` are development tools and fail this acceptance gate.

### 3. Online acceptance

With normal phone connectivity:

1. Launch the installed app without the laptop.
2. Confirm the device identity is stable across restart.
3. Open the SPEC-36 Laos corridor and its three city sections.
4. Open a driver card for each city.
5. Perform one later-city swap and confirm only the targeted city changes.
6. Confirm departure notification retrieval reaches the hosted provider-backed
   endpoint.
7. Confirm server logs contain no debug impersonation mode or secrets.

### 4. Offline acceptance

First load the corridor and driver cards online. Then disconnect USB and enable
airplane mode:

1. Force-kill and reopen the installed app.
2. Open the cached itinerary.
3. Expand each cached city/day section.
4. Open a pre-cached driver card with local name, landmark, and coordinates.
5. Record an offline-supported signal such as a heart.
6. Force-kill and reopen again; cached content and pending action remain.
7. Restore network; the pending action syncs once without duplication.

The test is invalid if any request can still reach a laptop through USB or a
local network tunnel.

## Non-goals

- OS push transport, which remains SPEC-27.
- Background GPS or continuous polling.
- Real offline map tiles.
- Meal-preview recommendations without provenance.
- New identity merge/account work from SPEC-24.
- App Store or Play Store public launch.
- New itinerary generation beyond SPEC-36.

## Required proof

- Backend CI and Flutter analyze/tests are green on the reviewed commit.
- Hosted health and authenticated trip reads succeed from a non-laptop
  network.
- The installed artifact reports the intended hosted base URL without
  displaying credentials.
- Online and airplane-mode results are recorded as a dated owner observation
  in `docs/AWAITING_VERIFICATION.md`.
- The exact build commit, platform, artifact delivery path, and hosted URL
  hostname are recorded. Secret values are not.

## Exit criteria

SPEC-37 is complete only when:

- SPEC-36 is merged;
- a stable hosted backend is healthy;
- an installable artifact runs independently on the owner's phone;
- the real corridor works online;
- cached itinerary and driver cards survive the offline drill; and
- queued offline activity drains exactly once after reconnect.
