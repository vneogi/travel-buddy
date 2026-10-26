# Genie brief: SPEC-43 Gap 5 -- exclude offline store from Android backup

Next after this lands: Gap 5 SQLCipher / Keystore (new brief).
Do not start SQLCipher, Gap 7, Gap 10, Gap 11, deploy, or an APK
without a new brief.

## Goal

The plaintext SQLite file `travel_buddy_offline.db` (and WAL/SHM)
plus SharedPreferences must not ride Android Auto Backup or
device-to-device transfer.

Today `android:allowBackup` is unset (platform default true). There
is no `fullBackupContent` or `dataExtractionRules`. iOS has no
file-sharing flag. SPEC-43 Gap 5 remaining after this slice:
SQLCipher, Keystore, paste-on-disk, masking.

This is SPEC-43 Gap 5 backup exclusion only. Clone the Gap 12 ATS
pattern (XML + a Dart file-read test). It is not SQLCipher, not
Keystore, not Gap 6 sign-out, not an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 5)
- `docs/briefs/GENIE_SPEC_43_G12_ATS.md` (file-read test pattern)
- `mobile/test/spec43_g12_ats_test.dart`
- `mobile/android/app/src/main/AndroidManifest.xml`
- `mobile/lib/offline/offline_database.dart` (`_dbName`)
- `docs/ENGINEERING_RULES.md` (R1, R14, R17)
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main` (`cafba3c`, PR #103).

Create and push:

`feat/spec43-g5-backup-exclusion`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 6 wipes rows on sign-out. A cloud or D2D backup taken before
that still restores trips, booking fields, outbox, and Ask threads
in plaintext. Encryption comes next; stop copying the file first.

## Current production seams to reuse

- Main `<application>` already has
  `android:networkSecurityConfig="@xml/network_security_config"`.
  Keep it. Add backup attributes next to it.
- Main `AndroidManifest.xml` may have a UTF-8 BOM. Do not strip it.
  Do not rewrite the whole file.
- Debug/profile manifests only add INTERNET. Do not set
  `allowBackup="true"` there.
- Do not change `OfflineDatabase`, sqflite, or Flutter emit.
- Do not run `flutter create`. Do not add an AppDelegate only to
  set `NSURLIsExcludedFromBackupKey` this slice.

## Scope

### 1. Android

On the main `<application>` tag set all three:

- `android:allowBackup="false"`
- `android:fullBackupContent="@xml/backup_rules"`
- `android:dataExtractionRules="@xml/data_extraction_rules"`

Add `mobile/android/app/src/main/res/xml/backup_rules.xml`
(`full-backup-content`):

- `<exclude domain="database" />` (covers `.db` + WAL/SHM)
- `<exclude domain="sharedpref" />`

Add `mobile/android/app/src/main/res/xml/data_extraction_rules.xml`:

- `<cloud-backup>` excludes `database` and `sharedpref`
- `<device-transfer>` excludes `database` and `sharedpref`
  (`allowBackup="false"` alone does not stop API 31+ D2D)

Do not `<include domain="root" />`. Do not allow any database path.

### 2. iOS (plist half only)

`ios/Runner/Info.plist`: assert `UIFileSharingEnabled` is not true
(absent or false). Do not invent `NSURLIsExcludedFromBackupKey` as
a plist key. File-level iOS exclusion waits on a later slice.

### 3. Tests

New file `mobile/test/spec43_g5_backup_test.dart`.

Directory.current is `mobile/`. Read files with `File.readAsStringSync`.
No widgets, no SQLite, no `pumpAndSettle`, no `physicalSize`.

Named test that must exist with this exact name:

`test_release_android_backup_excludes_offline_store`

It must fail if any of these are missing:

- main manifest contains `android:allowBackup="false"`
- main manifest does not contain `allowBackup="true"`
- main manifest references `@xml/backup_rules` and
  `@xml/data_extraction_rules`
- both XML files exist
- both XML files contain `domain="database"`
- both XML files contain `domain="sharedpref"`
- `data_extraction_rules.xml` contains `cloud-backup` and
  `device-transfer`

Also: Info.plist does not enable `UIFileSharingEnabled` as true.

No Python. No CREATE TABLE.

### 4. R17 sabotage

Exact edit: on the main `<application>` tag, change
`android:allowBackup="false"` to `android:allowBackup="true"`.

`test_release_android_backup_excludes_offline_store` must fail.
Restore before the PR. Do not sabotage by deleting the test.
Do not sabotage ATS XML.

## Out of scope

- SQLCipher, Keystore, Keychain, passphrase
- Masking booking refs, task-switcher, screenshot policy
- Changing `deleteAllLocalRows` or Gap 6
- Hosted 0026, Gap 1 Cloud Run, APK
- iOS `NSURLIsExcludedFromBackupKey` on the file

## Gates

Genie (if Flutter SDK exists) or the owner Windows laptop:

```
cd mobile
flutter analyze
flutter test
```

If Genie has no Flutter SDK: push the XML/manifest/test files,
report that, and stop. Do not merge. The owner runs Flutter.

R1: after any Dart write, `grep -rn '\\$' mobile/lib` -- only the
two price strings in `upgrade_screen.dart`.

## Report

SHA, branch, files touched. Named test name in the report must be
`test_release_android_backup_excludes_offline_store`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
