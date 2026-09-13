# Genie Brief: SPEC-37 review corrections after 0f83a86

> Continue `feat/spec37-phone-field-test` and draft PR #57. Do not deploy or merge.
> CI `android-compile` is red on `0f83a86`. Python pytest is not evidence the APK builds.

## Root cause (must read)

Hand-written Android files were emitted from Python heredocs. The tree contains
literal backslash-dollar interpolations:

- `mobile/android/settings.gradle` -- `includeBuild("\${flutterSdkPath}/...")`
- `mobile/android/build.gradle` -- `project.buildDir = "\${rootProject.buildDir}/..."`
- `mobile/android/app/src/main/AndroidManifest.xml` -- `android:name="\${applicationName}"`

Gradle/XML need `${name}`, not `\${name}`. This is the Dart R1 failure in Groovy.
After ANY write of Android files, grep the tree:

```bash
rg -n '\\\$' mobile/android
```

Allowed: `https\\://` in `gradle-wrapper.properties` only. Any other `\\$` is a bug.

Also missing: `gradle-wrapper.jar` and `@mipmap/ic_launcher` resources.
`android:icon="@mipmap/ic_launcher"` cannot link without those mipmaps.

Do not reconstruct the Android platform from Python again.

## Must fix

### 1. Make `flutter build apk --debug` actually succeed

Preferred: generate the platform with Flutter, then overlay project settings.

From `mobile/` on a machine with the Flutter SDK (or document that you could not
and stop -- do not invent another broken scaffold):

```bash
flutter create . --platforms=android --org com.vneogi --project-name travel_buddy
```

Then overlay only:

- `applicationId` / `namespace` = `com.vneogi.travelbuddy`
- `INTERNET` on the **main** manifest
- release signing from gitignored `key.properties` (release must not silently
  use the debug key when `key.properties` is present)
- keep `lib/`, `test/`, `pubspec.yaml`, and assets untouched

If Flutter is unavailable in your environment, fix the three `\\$` interpolations
AND add a compile-safe launcher icon (do not reference a missing mipmap). Then
still require CI `android-compile` green before claiming item 1 done.

Do not enable R8 minify/shrink on the first field-test APK unless you also ship
Flutter plugin keep rules. A minified first APK that crashes on launch fails
SPEC-37. Default minify off for this slice.

### 2. Prove Env.apiHostname for a hosted URL (R17)

`mobile/test/env_host_test.dart` second test parses a literal `Uri` and never
calls `Env`. Extract a pure helper, e.g. `hostnameFromBaseUrl(String url)`,
used by `Env.apiHostname`, and assert:

- `https://travel-buddy-field.run.app` -> `travel-buddy-field.run.app`
- default local URL is not claimed as the hosted host

A `Uri.parse` of a string you just wrote is not a proof.

### 3. Fix the Anonymous UUID in `docs/CLOUD_RUN_DEPLOY.md`

Do not generate the UUID with `Get-Random` formatted as hex. That can emit the
wrong length and fail SPEC-09 canonical UUID-v4 validation.

Use a fixed valid example:

```text
aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
```

Keep `Authorization: Anonymous <uuid>`. Assert HTTP 200. PowerShell: use
`curl.exe` as in `docs/HOSTED_STATE.md` if `Invoke-RestMethod` hides status.

### 4. Confirm health stayed liveness-only

`/health` must not grow `debug_mode` / key-presence fields again. Config proof
remains startup logs and the Cloud Run revision panel.

## Gates (report all)

```bash
pytest -q -ra
ruff check .
ruff format --check .
git diff --check
rg -n '\\\$' mobile/android
```

CI on PR #57 must show `android-compile` **success** and `docker-build` success.
Do not report a file inspection as an APK pass. If Flutter is unavailable to
you, wait for CI; if CI is red, fix from the job log.

## Completion

Push the same branch. Do not merge. Do not tell the owner to `gcloud run deploy`
or `flutter build apk --release` until `android-compile` is green on the PR.
Report the new full SHA and the CI conclusions. Stop.
