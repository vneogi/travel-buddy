# Genie brief: SPEC-43 Gap 5 -- SQLCipher the offline store

Do not start Gap 7, Gap 10, Gap 11, masking, lock-screen,
deploy, or an APK without a new brief.

## Goal

Production Android and iOS must open `travel_buddy_offline.db` with
SQLCipher. The passphrase lives in `FlutterSecureStorage` (Android
Keystore / iOS Keychain). Never open that file without a password.
Never catch a decrypt failure and retry as plaintext.

This is SPEC-43 Gap 5 SQLCipher only. Clone the Gap 12 ATS / Gap 5
backup pattern: a Dart file-read test the Windows laptop can run.
It is not Keystore JNI, not masking, not Gap 6, not an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 5)
- `docs/briefs/GENIE_SPEC_43_G5_BACKUP.md` (landed; do not redo)
- `mobile/lib/offline/offline_database.dart` (`_open`, `_dbName`)
- `mobile/lib/offline/db_init.dart` (conditional factory)
- `mobile/lib/core/device_identity.dart` (secure-storage pattern)
- `mobile/pubspec.yaml` (`sqflite`, `flutter_secure_storage`)
- `docs/ENGINEERING_RULES.md` (R1, R14, R17)
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main` (`1672759`, PR #105).

Create and push:

`feat/spec43-g5-sqlcipher`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Backup exclusion (`1672759`) stops Auto Backup from copying the
file. The file on the phone is still ordinary SQLite. A stolen
device, debugger, or `adb pull` can read trips, booking fields,
outbox, and Ask threads as UTF-8.

`FlutterSecureStorage` is already a dependency (device UUID). Use it
for the DB key. Do not invent a native Keystore plugin this slice.

## Current production seams to reuse

- `OfflineDatabase._open` calls `openDatabase` from `package:sqflite`
  with no password. Tests pass `testPath` (in-memory URI). Keep that
  unencrypted test path.
- Web (`kIsWeb`) and desktop FFI stay unencrypted this slice.
  Encrypt only Android and iOS production opens.
- Do not import `dart:io` into `offline_database.dart` (web compile).
  Put Platform / sqlcipher behind a conditional export, same idea as
  `db_init.dart`.
- Do not use `tb_device_uuid` as the database password.
- Do not strip the UTF-8 BOM on `AndroidManifest.xml`.
- Do not change backup XML or `allowBackup`.

## Scope

### 1. Passphrase helper

New file `mobile/lib/offline/offline_db_key.dart`.

- Storage key constant: `tb_offline_db_key`
- Inject `FlutterSecureStorage` (same pattern as `DeviceIdentity`)
- `getOrCreate()`: if a non-empty value exists, return it; else
  generate 32 cryptographically random bytes, persist as hex
  (64 chars), return it
- Concurrent callers share one in-flight Future
- If storage read/write throws, rethrow. Do not invent a fallback
  key. Do not log the key.

### 2. Production open

Keep `sqflite` for the `Database` type and FFI tests.

Add `sqflite_sqlcipher` (compatible with current `sqflite` 2.3.x).
`flutter pub get`. If the two plugins clash, keep `sqflite` and call
sqlcipher `openDatabase` only from the IO helper below.

New conditional export:

- `mobile/lib/offline/offline_open.dart`
- stub (web / default): existing unencrypted `openDatabase`
- `dart.library.io`: Android/iOS uses sqlcipher with `password:`;
  other IO (Windows/macOS/Linux) stays unencrypted `openDatabase`

`OfflineDatabase._open`:

- if `_testPath != null`: existing unencrypted `openDatabase` (tests)
- else: call the helper with path, version, onCreate, onUpgrade

IO helper for Android/iOS:

1. `final key = await OfflineDbKey().getOrCreate();`
2. `openDatabase(path, password: key, version: ..., onCreate, onUpgrade)`
   using `sqflite_sqlcipher`
3. If that throw looks like "file is not a database" / HMAC /
   not-encrypted leftover from before this slice: delete `path`,
   `path-wal`, `path-shm` if present, then open WITH `password:`
   again once
4. Never retry without `password:`
5. Never swallow the error into a plaintext open

Do not migrate plaintext rows. Owner device recaches after wipe.

Do not change schema version unless sqlcipher requires it. Prefer
keeping `_dbVersion = 9`.

### 3. Tests

New file `mobile/test/spec43_g5_sqlcipher_test.dart`.

Directory.current is `mobile/`. Read files with `File.readAsStringSync`.
No widgets, no SQLite open, no `pumpAndSettle`, no `physicalSize`.
Do not assert on comments.

Named test that must exist with this exact name:

`test_production_offline_open_passes_sqlcipher_password`

It must fail if any of these are missing:

- `pubspec.yaml` contains `sqflite_sqlcipher`
- `lib/offline/offline_db_key.dart` exists
- that file contains `tb_offline_db_key`
- that file contains `FlutterSecureStorage`
- IO open helper source contains `password:`
- IO open helper source does not contain a catch that calls
  `openDatabase` without `password:`
- `offline_database.dart` still uses `_dbName = 'travel_buddy_offline.db'`

Also a small extra test is fine (pubspec + helper files exist).
Do not assert that XML comments omit the db filename.

No Python. No CREATE TABLE. No Gap 6 wipe changes.

### 4. R17 sabotage

Exact edit: in the Android/iOS production open call, delete the
`password:` named argument (leave `openDatabase(path, version: ...)`).

`test_production_offline_open_passes_sqlcipher_password` must fail.
Restore before the PR. Do not sabotage by deleting the test.
Do not sabotage backup XML or ATS XML.

## Out of scope

- Masking booking refs, task-switcher, screenshot / FLAG_SECURE
- iOS `NSFileProtectionComplete` / `NSURLIsExcludedFromBackupKey`
- Changing `deleteAllLocalRows` or Gap 6
- Encrypting Windows FFI / web
- Hosted 0026, Gap 1 Cloud Run, APK
- Native Keystore JNI beyond `FlutterSecureStorage`

## Gates

Genie (if Flutter SDK exists) or the owner Windows laptop:

```
cd mobile
flutter pub get
flutter analyze
flutter test
```

If Genie has no Flutter SDK: push the Dart/pubspec files, report
that, and stop. Do not merge. The owner runs Flutter.

R1: after any Dart write, `grep -rn '\\$' mobile/lib` -- only the
two price strings in `upgrade_screen.dart`.

## Report

SHA, branch, files touched. Named test name in the report must be
`test_production_offline_open_passes_sqlcipher_password`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
