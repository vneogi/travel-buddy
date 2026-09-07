# Android Signed APK Build Guide (SPEC-37)

Build an installable Android APK that points at the hosted Cloud Run backend.
No emulator, no `flutter run`, no laptop required after install.

## Prerequisites

- Flutter SDK installed (stable channel, 3.22+)
- Android SDK with build-tools and platform 34+
- A USB-connected Android phone with Developer Options and USB Debugging enabled

## 1. Pull the reviewed commit and verify (PowerShell)

```powershell
cd travel-buddy
git fetch origin
git checkout feat/spec37-phone-field-test
git pull origin feat/spec37-phone-field-test
git log -1 --oneline
# Confirm the SHA matches the reviewed commit
```

## 2. Create a signing keystore (one-time, PowerShell)

```powershell
keytool -genkey -v `
  -keystore "$HOME\travel-buddy-release.jks" `
  -keyalg RSA -keysize 2048 -validity 10000 `
  -alias travel-buddy
```

Enter the keystore password when prompted. Do not commit the keystore or
passwords to the repository. Keep this keystore for future upgrades: the same
application ID (`com.vneogi.travelbuddy`) and signing key must be retained.

## 3. Create `mobile/android/key.properties` (gitignored)

```powershell
@"
storePassword=<your-keystore-password>
keyPassword=<your-key-password>
keyAlias=travel-buddy
storeFile=$HOME\travel-buddy-release.jks
"@ | Set-Content mobile\android\key.properties -Encoding UTF8
```

Do not print or commit this file. It is already in `.gitignore`.

## 4. Build the signed release APK (PowerShell)

```powershell
cd mobile
flutter pub get
flutter build apk --release `
  --dart-define=TB_API_BASE_URL=https://<your-service>.run.app
```

The APK is output to:

```text
build/app/outputs/flutter-apk/app-release.apk
```

## 5. Locate the APK SHA-256 fingerprint

```powershell
certutil -hashfile build\app\outputs\flutter-apk\app-release.apk SHA256
```

Record this in the PR for traceability (no secrets).

## 6. Install on the phone

With the phone connected via USB:

```powershell
adb install build\app\outputs\flutter-apk\app-release.apk
```

If upgrading over a previous debug install, uninstall first (different signing
key):

```powershell
adb uninstall com.vneogi.travelbuddy.debug
adb install build\app\outputs\flutter-apk\app-release.apk
```

## 7. Disconnect and verify

1. Disconnect the USB cable.
2. Close any `adb reverse` or local tunnel.
3. Launch Travel Buddy from the phone home screen.
4. The app connects to the Cloud Run backend over HTTPS.
5. No localhost, `10.0.2.2`, or LAN addresses involved.

## What to record in the PR (no secrets)

| Field | Value |
|---|---|
| Source commit SHA | |
| Platform | Android |
| Artifact | Signed release APK |
| Hosted API hostname | (e.g. travel-buddy-xxxxx.run.app) |
| Build command | `flutter build apk --release --dart-define=TB_API_BASE_URL=https://<host>` |
| APK SHA-256 | |
