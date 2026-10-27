# Genie brief: SPEC-43 Gap 12 -- Android network security and iOS ATS

Landed on `main` as `be89128` (PR #92). Do not re-implement this slice.
Deep-link ownership landed as `f486079`. Gap 9 schemas `fb72545`.
Next: `docs/briefs/GENIE_SPEC_43_G5_SQLCIPHER.md`.

## Goal

Release traffic must be TLS-only at the OS policy layer, not only in
Dart `assertSecureTransport`. Debug may talk HTTP to the emulator
loopback. Release must not.

There is no `network_security_config.xml`. Main
`AndroidManifest.xml` does not set `networkSecurityConfig`. There is
no iOS tree on `main` (only a gitignore line for
`GoogleService-Info.plist`). ATS is therefore undeclared.

This is SPEC-43 Gap 12 ATS / network-security XML only. HTTPS
fail-closed (`6f1dab8`), cache keys (`290f821`), and chat URLs
(`14ce56d`) are already on main. Do not re-implement them. This is
not custom URL schemes, intent VIEW filters, App Links, universal
links, deep-link ownership, Gap 5 SQLCipher, deploy, or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 12)
- `mobile/android/app/src/main/AndroidManifest.xml`
- `mobile/android/app/src/debug/AndroidManifest.xml`
- `mobile/android/app/src/profile/AndroidManifest.xml`
- `mobile/lib/core/env.dart` (`http://10.0.2.2:8000` debug default;
  do not change it)
- `docs/ENGINEERING_RULES.md` (R1, R14, R17)
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including chat URLs `14ce56d` (PR #89)
and docs `99660b6` (PR #90).

Create and push:

`feat/spec43-g12-ats`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

SPEC-43 Gap 12: declare Android network security and iOS ATS
explicitly. Do not use a permissive release exception for the
emulator development URL. Dart already rejects HTTP in release.
A missing XML still lets a future HTTP client or WebView bypass that.

## Current production seams to reuse

- Debug API default `http://10.0.2.2:8000` in `Env.apiBaseUrl`. Keep
  it. Do not switch the default to https.
- `assertSecureTransport` already fails closed in release. Leave it.
- Debug and profile manifests currently add INTERNET only. Keep that
  permission.

Do not add `android:usesCleartextTraffic="true"` on the main
application. Do not add a release `domain-config` for `10.0.2.2`.
Do not run `flutter create` to generate a full iOS project.

## Scope

### 1. Android release policy

Add `mobile/android/app/src/main/res/xml/network_security_config.xml`:

- `base-config` with `cleartextTrafficPermitted="false"`
- system trust anchors only
- no domain that permits cleartext
- the file must not contain `10.0.2.2`, `localhost`, or `127.0.0.1`

On the main `<application>` tag, set
`android:networkSecurityConfig="@xml/network_security_config"`.

### 2. Android debug and profile overlay

Android resource overlay: same resource name in
`mobile/android/app/src/debug/res/xml/network_security_config.xml`
and `mobile/android/app/src/profile/res/xml/network_security_config.xml`.

Those overlays:

- keep `base-config` `cleartextTrafficPermitted="false"`
- add a `domain-config` with `cleartextTrafficPermitted="true"` only
  for `10.0.2.2`, `localhost`, and `127.0.0.1`
- no other cleartext domains

Do not set global `usesCleartextTraffic="true"` on debug/profile
application tags.

### 3. iOS ATS declaration

`main` has no `mobile/ios/` sources. Add only:

`mobile/ios/Runner/Info.plist`

Valid XML plist. Must include `NSAppTransportSecurity` with
`NSAllowsArbitraryLoads` false. Must not add `NSExceptionDomains`
(or any other exception) for `10.0.2.2` or other HTTP hosts.

Do not add a full Xcode project, CocoaPods, or
`GoogleService-Info.plist`. A future iOS `flutter create` must keep
this ATS dict.

### 4. Tests

New file `mobile/test/spec43_g12_ats_test.dart`.

Read the XML and plist from disk. No widgets, no `pumpAndSettle`,
no `physicalSize`, no SQLite, no network. `Directory.current` in
`flutter test` is `mobile/`.

Named test that must exist with this exact name:

`test_release_network_security_config_forbids_cleartext`

It must:

1. Read `android/app/src/main/res/xml/network_security_config.xml`.
2. Assert it contains `cleartextTrafficPermitted="false"`.
3. Assert it does not contain `cleartextTrafficPermitted="true"`.
4. Assert it does not contain `10.0.2.2`.

Add further tests (names yours) that:

- main `AndroidManifest.xml` references `@xml/network_security_config`
- debug overlay XML permits cleartext for `10.0.2.2`
- profile overlay XML matches that debug exception
- `ios/Runner/Info.plist` has `NSAllowsArbitraryLoads` false and no
  `10.0.2.2`

## Out of scope

- Custom URL schemes, intent VIEW filters, App Links, universal links
- Authorizing `/trip/:tripId` against the current identity (next brief)
- Changing `assertSecureTransport` or chat `extra`
- SQLCipher, RLS apply, Gap 1 Cloud Run deploy, APK
- Hardcoding USD prices (R1)

## R17 sabotage (owner laptop, after your report)

Exact edit, not a one-word swap:

In `mobile/android/app/src/main/res/xml/network_security_config.xml`,
change the release `base-config` to
`cleartextTrafficPermitted="true"`.

`test_release_network_security_config_forbids_cleartext` must fail
because release XML now permits cleartext. A test that only checks
the manifest attribute and ignores the XML is the wrong test.

Restore the file before the PR.

Do not sabotage by deleting the test.

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

SHA, branch, pytest last line, analyze, flutter test, files touched.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.

R1: `rg '\$' mobile/lib --glob '*.dart'` must not gain a price.
XML/plist work is not Dart prices. Do not add `$29`.
