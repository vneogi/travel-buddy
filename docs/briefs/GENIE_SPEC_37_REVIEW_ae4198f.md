# Genie Brief: SPEC-37 android-compile still red on ae4198f

> Continue `feat/spec37-phone-field-test` and draft PR #57. Do not deploy or merge.

The `\${` interpolations, minify-off, framework icon, UUID, and
`hostnameFromBaseUrl` helper are in the tree. That was necessary and not
sufficient.

CI on `ae4198fee08211cf4cea2c5c62260d7a524d7c28`:

- pytest, lint, flutter, docker-build: success
- **android-compile: failure** (job 101614639427, ~2m 19s)

Read that job log. Do not guess. Do not report pytest as an APK pass.

## Must fix

Hand-written `mobile/android/` still has no `gradle-wrapper.jar` and no
Flutter-generated launcher/drawables. Plugin pins in `settings.gradle`
(AGP 8.7.0, Kotlin 2.1.0) were invented, not taken from the Flutter SDK that
CI installs via `subosito/flutter-action@v2` channel stable.

Preferred repair, on a machine with Flutter (or by making CI generate and you
commit the result -- do not leave the platform as Python output):

```bash
cd mobile
flutter create . --platforms=android --org com.vneogi --project-name travel_buddy
```

Keep `lib/`, `test/`, `pubspec.yaml`. Overlay only:

- `applicationId` / `namespace` = `com.vneogi.travelbuddy`
- `INTERNET` on the **main** manifest
- release signing from gitignored `key.properties`
- `minifyEnabled false` / `shrinkResources false` for this first APK

Commit `gradle-wrapper.jar` (binary). After writes, confirm interpolations are
`${...}` not `\${...}`. Allowed exception: `https\://` in
`gradle-wrapper.properties`.

If you cannot run Flutter, stop and say so. Another hand-written Gradle file
is not the fix.

## Already acceptable (do not reopen)

- `/health` liveness-only
- Cloud Run docs Anonymous header + fixed UUID
- `hostnameFromBaseUrl` used by `Env.apiHostname`

## Gates

Local Python gates plus **CI `android-compile` success** on the new SHA.
Push the same branch. Report the SHA and the CI conclusions. Stop.
