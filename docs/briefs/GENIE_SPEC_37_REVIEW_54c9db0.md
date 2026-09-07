# Genie Brief: SPEC-37 review corrections after 54c9db0

> Continue `feat/spec37-phone-field-test` and PR #57. Do not deploy or merge.
> Review was performed against `54c9db0`; read the current branch before editing.

## Cleared

- Android is the owner-selected platform.
- The Google Maps key was rotated and the old key revoked.
- Cloud Run is the selected container target.
- The branch starts from reviewed main after SPEC-36.
- `.env` and mobile sources are excluded from the backend build context.

## Must fix before owner deployment

### 1. Add the Android platform; the repository currently cannot build an APK

`mobile/` tracks only Dart sources and assets. It has no `mobile/android/`.
`flutter build apk` in `docs/ANDROID_BUILD.md` therefore cannot work.

Generate and commit only the Android platform for the existing app. Use a stable
application ID: `com.vneogi.travelbuddy`. Do not regenerate or overwrite `lib/`,
`test/`, `pubspec.yaml`, or assets. Inspect the diff after generation.

The release app must declare `android.permission.INTERNET` in the main manifest,
not only debug/profile. Add release signing that reads the already-gitignored
`mobile/android/key.properties`. A release build must not silently use the debug
key. Keep keystores and passwords untracked.

Add a CI Android compile proof (debug APK is sufficient for CI; the owner-signed
release APK remains an owner gate). The CI build must pass a non-local HTTPS
`TB_API_BASE_URL` so the generated Android platform is exercised.

### 2. Correct hosted authentication verification

`docs/CLOUD_RUN_DEPLOY.md` uses `X-Device-ID`. Production does not accept that
header. It requires:

```text
Authorization: Anonymous <canonical-lowercase-UUID-v4>
```

Replace both protected curls with a canonical UUID-v4 and the Anonymous header.
Assert HTTP 200 rather than printing an unchecked body. Keep
`TB_ALLOW_ANONYMOUS=true` and `TB_SUPABASE_JWT_SECRET` unset.

### 3. Do not publish configuration state in the public health body

Revert the additions to `routers/trip_router.py` (`debug_mode`,
`llm_key_present`, `supabase_configured`, `jwt_auth`). `/health` is public and
only needs to prove liveness. Existing startup logs already print those booleans
without values. Cloud Run revision configuration plus startup logs are the proof.
Do not expose backend configuration to unauthenticated callers.

Update the deployment guide and acceptance wording accordingly.

### 4. Make Cloud Run deployment commands operable and region-neutral

Do not hardcode `us-central1`; no project region was verified. Use a required
`REGION` placeholder/variable selected by the owner, with a command to list Cloud
Run regions. Prefer a region close to the hosted Supabase database to reduce
backend latency.

The current `gcloud builds submit --tag .../cloud-run-source-deploy/...` assumes
an Artifact Registry repository already exists. Either create and verify the
repository explicitly, or use `gcloud run deploy --source .` so the documented
path is complete. Provide Windows PowerShell commands because that is the
owner's laptop shell; Cloud Shell commands may be a separate optional section.

Do not claim that a server-side Cloud Run Maps key can retain an incompatible
Android application restriction. It must retain API restrictions; any
application restriction must be compatible with Cloud Run egress. Verify the
provider from the hosted service.

### 5. Make the Android guide complete and correct for Windows

Add full PowerShell steps: pull and verify SHA, create keystore with a Windows
path, create `key.properties` without printing secrets, build, locate SHA-256,
install, disconnect USB, and launch from the phone home screen.

From `mobile/`, the APK install path is
`build/app/outputs/flutter-apk/app-release.apk`, not
`mobile/build/app/outputs/flutter-apk/app-release.apk`.

Add a clean-install/upgrade note: the same application ID and signing key must
be retained for future upgrades.

### 6. Implement the required API-host proof

SPEC-37 requires the installed artifact to report the intended hosted base URL
without credentials. Currently `Env.apiBaseUrl` is used only inside ApiClient.
Add a small read-only build diagnostic in Profile/About showing the API hostname
only (for example `service-name.run.app`, not a query string or credentials).
Add a test proving a non-local host is rendered. This is delivery diagnostics,
not a new consumer feature.

### 7. Restore documentation ownership

Remove the blank future acceptance template appended to
`docs/AWAITING_VERIFICATION.md`. That file owns dated observations, not an
unsigned future checklist. `docs/TESTING_GUIDE.md` section 6 owns the final
acceptance procedure; make the complete owner steps there (or link to the build
and deploy guides without copying a second checklist). After the owner actually
runs it, append one dated finding to `AWAITING_VERIFICATION.md`.

## Gates

Run and report:

```bash
pytest -q -ra
ruff check .
ruff format --check .
git diff --check
```

From `mobile/` with Flutter available:

```bash
flutter pub get
flutter analyze --no-fatal-infos
flutter test
flutter build apk --debug --dart-define=TB_API_BASE_URL=https://example.invalid
```

Also build the Docker image in CI on the PR. A Python test suite does not prove
the Dockerfile builds. Report skips with reasons.

## Completion

Push the same branch and update draft PR #57. Do not deploy, build the owner's
signed APK, or merge. Report the new full SHA, exact gates, and any decision the
owner still needs to make. Stop.
