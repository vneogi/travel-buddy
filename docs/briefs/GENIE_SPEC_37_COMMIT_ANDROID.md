# Genie Brief: commit Windows Android platform, then stop

> Continue draft PR #57 on `feat/spec37-phone-field-test`. Do not merge.
> Do not `gcloud run deploy`. Do not regenerate `mobile/android/` with
> `flutter create` in CI or from Python.

## What the owner already proved (2026-09-12)

Windows laptop, Flutter 3.44.8 stable:

- `flutter test` passed
- `flutter build apk --debug --dart-define=TB_API_BASE_URL=https://example.invalid`
  succeeded
- applicationId / namespace / MainActivity: `com.vneogi.travelbuddy`
- INTERNET on the main manifest
- `isMinifyEnabled = false` and `isShrinkResources = false`
- `app/build.gradle.kts` uses the Kotlin `compilerOptions` DSL (AGP 9)
- PowerShell `Set-Content -Encoding utf8` BOM on Gradle files breaks the build;
  do not rewrite Gradle that way

`example.invalid` is compile proof only. The field APK is not this file.

## Must land in git (same PR)

The owner's `C:\Users\ariav\travel-buddy\mobile\android\` must be committed
(including `gradle-wrapper.jar` and launcher mipmaps). Root `.gitignore` must
not ignore all of `mobile/android/`. Ignore only `local.properties`,
`key.properties`, and keystores.

CI `android-compile` must build the committed platform. No `flutter create`.
No `scripts/overlay_android.sh`. Pin Flutter 3.44.8 to match the laptop.

Do not add `mobile/ios/`, dummy `test/widget_test.dart`, `mobile/.metadata`,
or generated l10n dumps from `flutter create`.

## After that commit is on GitHub

Wait for PR #57 `android-compile` **success**. Then, and only then:

1. Kotlin DSL release signing that loads gitignored `key.properties` and fails
   clearly if the keystore is missing (do not silently sign release with debug)
2. Owner Cloud Run deploy in `asia-south1` per `docs/CLOUD_RUN_DEPLOY.md`
3. Owner signed APK with the real `*.run.app` URL per `docs/ANDROID_BUILD.md`

If the owner has already pushed `mobile/android/` and CI is red, fix from the
job log. Do not invent another overlay script.

## Gates

```bash
pytest -q -ra
ruff check .
ruff format --check .
git diff --check
```

Plus GitHub `android-compile` success on the SHA that contains `mobile/android/`.
Push the same branch. Report that SHA and the CI conclusions. Stop.
