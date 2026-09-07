# Android Signed APK Build Guide (SPEC-37)

Build an installable Android APK that points at the hosted Cloud Run backend.
No emulator, no `flutter run`, no laptop required after install.

## Prerequisites

- Flutter SDK installed (3.22+ recommended)
- Android SDK with build-tools
- A signing keystore (create one if needed; do not commit it)

## 1. Create a signing keystore (one-time)

```bash
keytool -genkey -v -keystore ~/travel-buddy-release.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias travel-buddy
```

Enter the keystore password when prompted. Do not commit the keystore or
passwords to the repository.

## 2. Configure signing in `android/key.properties`

Create `mobile/android/key.properties` (gitignored):

```properties
storePassword=<your-keystore-password>
keyPassword=<your-key-password>
keyAlias=travel-buddy
storeFile=<path-to>/travel-buddy-release.jks
```

## 3. Build the signed APK

From the `mobile/` directory:

```bash
flutter build apk --release \
  --dart-define=TB_API_BASE_URL=https://<your-service>.run.app
```

The APK is output to `mobile/build/app/outputs/flutter-apk/app-release.apk`.

## 4. Install on the phone

Transfer and install:

```bash
adb install mobile/build/app/outputs/flutter-apk/app-release.apk
```

After installation, disconnect the USB cable. The app must work independently.

## 5. Verify

- Launch from the phone home screen (laptop closed/off)
- The app should connect to the Cloud Run backend over HTTPS
- No localhost, 10.0.2.2, or LAN addresses involved

## What to record in the PR (no secrets)

- Source commit SHA
- Platform: Android
- Artifact: signed release APK
- Hosted API hostname (e.g., travel-buddy-xxxxx.run.app)
- Build command (with --dart-define, without secret values)
