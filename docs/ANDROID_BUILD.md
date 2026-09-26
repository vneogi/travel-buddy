# Android Signed APK Build Guide (SPEC-37)

Build an installable Android APK that points at the hosted Cloud Run backend.
No emulator, no `flutter run`, no laptop required after install.

For the final 1 October owner field artifact, use this guide together with
`docs/briefs/PRE_LAOS_FINAL_RUNBOOK.md`. That runbook fixes the order:
SPEC-44 proof/merge, hosted 0025, Cloud Run deploy, test-trip purge, Windows
gates, app-data clear, signed build, install, and online/offline phone matrix.

The Android platform under `mobile/android/` is committed. Do not run
`flutter create` in CI. Do not regenerate the platform unless Flutter's
Android template must be refreshed, and then commit the result.

## Prerequisites

- Flutter SDK 3.44.8 (stable), matching the owner's Windows compile proof
- Android SDK with build-tools and platform 34+
- A USB-connected Android phone with Developer Options and USB Debugging enabled
  (USB is only for `adb install`; disconnect before acceptance)

## Current local compile proof (2026-09-12)

On the owner's Windows laptop, Flutter 3.44.8 built:

```text
flutter build apk --debug --dart-define=TB_API_BASE_URL=https://example.invalid
```

That APK is a compile proof only. `example.invalid` does not resolve. Do not
sideload it as the field-test artifact.

Settled identity:

- applicationId / namespace / MainActivity package: `com.vneogi.travelbuddy`
- INTERNET on the main manifest
- release minify and resource shrinking off

## 1. Pull the reviewed commit (PowerShell)

```powershell
cd travel-buddy
git fetch origin
git checkout main
git pull origin main
git log -1 --oneline
```

Confirm `mobile/android/` is tracked, including `gradle-wrapper.jar`.

## 2. Create a signing keystore (one-time, after CI android-compile is green)

Skip this until GitHub `android-compile` is green and Cloud Run has a URL.

```powershell
keytool -genkey -v `
  -keystore "$HOME\travel-buddy-release.jks" `
  -keyalg RSA -keysize 2048 -validity 10000 `
  -alias travel-buddy
```

Do not commit the keystore or passwords. Keep the same application ID and
signing key for future upgrades.

## 3. Create `mobile/android/key.properties` (gitignored)

```powershell
@"
storePassword=<your-keystore-password>
keyPassword=<your-key-password>
keyAlias=travel-buddy
storeFile=$HOME\travel-buddy-release.jks
"@ | Set-Content mobile\android\key.properties -Encoding UTF8
```

Do not print or commit this file. Release Gradle must load it (Kotlin DSL) and
fail clearly if it is missing. Until that wiring is committed, `flutter build
apk --release` may still sign with the debug key -- that is not the field APK.

PowerShell `Set-Content -Encoding utf8` adds a BOM. Never use it on
`build.gradle.kts` or other Gradle/Kotlin files.

## 4. Build the signed release APK (after Cloud Run exists)

```powershell
cd mobile
flutter pub get
flutter build apk --release `
  --dart-define=TB_API_BASE_URL=https://<your-service>.asia-south1.run.app
```

APK path (from `mobile/`):

```text
build\app\outputs\flutter-apk\app-release.apk
```

## 5. Record the APK SHA-256 (no secrets)

```powershell
certutil -hashfile build\app\outputs\flutter-apk\app-release.apk SHA256
```

## 6. Install, then disconnect

```powershell
adb install build\app\outputs\flutter-apk\app-release.apk
```

If a previous debug install exists:

```powershell
adb uninstall com.vneogi.travelbuddy.debug
adb install build\app\outputs\flutter-apk\app-release.apk
```

Then disconnect USB, close any `adb reverse` or local tunnel, and launch from
the phone home screen. Profile > API Host must show the Cloud Run hostname.

For a deliberately clean owner field session, stop the old app and clear its
SQLite caches, outbox, secure-storage identity, and prior state before the
final install:

```powershell
adb shell am force-stop com.vneogi.travelbuddy
adb shell pm clear com.vneogi.travelbuddy
adb install -r build\app\outputs\flutter-apk\app-release.apk
```

This creates a fresh anonymous device identity on next launch. Run the hosted
trip purge first and do not reopen the old APK between purge and clear.

## What to record in the PR (no secrets)

Field APK used 2026-09-14 (owner did not paste certutil hash):

| Field | Value |
|---|---|
| Source commit SHA | `fefc4ec` |
| Platform | Android |
| Artifact | Signed release APK |
| Hosted API hostname | `travel-buddy-196190001420.asia-south1.run.app` |
| Build command | `flutter build apk --release --dart-define=TB_API_BASE_URL=https://travel-buddy-196190001420.asia-south1.run.app` |
| APK SHA-256 | (not recorded) |
