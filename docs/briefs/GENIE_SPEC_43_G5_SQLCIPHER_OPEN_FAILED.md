# Genie brief: SPEC-43 Gap 5 -- treat SQLCipher open_failed as leftover DB

Do not start Gap 7, masking, lock-screen, 0026, deploy, or an APK
without a new brief.

## Goal

When SQLCipher cannot decrypt `travel_buddy_offline.db`, treat that
as an unreadable leftover file: delete db/WAL/SHM/journal and open
again WITH `password:`. Never retry without a password. Never leave
the exception uncaught so `main()` never reaches `runApp`.

Owner G0 phone 2026-10-31: HMAC failed on page 1 of the pre-SQLCipher
plaintext file. `sqflite_sqlcipher` wrapped it as
`DatabaseException(open_failed .../travel_buddy_offline.db)`.
`_isUnreadableWithKey` did not match, so the catch rethrew, splash
stuck. `adb shell pm clear com.vneogi.travelbuddy` unblocked the
owner. An upgrade must not require that.

This is SPEC-43 Gap 5 SQLCipher leftover-open only. Clone the
existing file-read test. It is not Keystore JNI, not Gap 7, not
an APK.

Read before editing:

- `mobile/lib/offline/offline_open_io.dart`
- `mobile/test/spec43_g5_sqlcipher_test.dart`
- `docs/briefs/GENIE_SPEC_43_G5_SQLCIPHER.md` (landed; do not redo)
- `docs/ENGINEERING_RULES.md` (R1, R14, R17)

Base branch: latest `main` (`1aa405c`).

Create and push:

`feat/spec43-g5-sqlcipher-open-failed`

Do not merge. Open one PR only after the gates below are green.

## Scope

### 1. Matcher

In `_isUnreadableWithKey`, also return true when the lowercased
error string contains:

- `open_failed`
- `file is encrypted`

Keep the existing hmac / not-a-database / sqlite_notadb / code 26
checks. Do not treat every DatabaseException as leftover.

### 2. Fail closed on splash

`openOfflineStore` already catches, deletes, and retries with
password when the matcher hits. After this change, `open_failed`
must take that path.

Do not wrap `main()` in an empty catch. Do not open without
`password:` on Android/iOS.

### 3. Tests

Edit `mobile/test/spec43_g5_sqlcipher_test.dart`.

Named test that must exist with this exact name:

`test_production_offline_open_passes_sqlcipher_password`

It must still require `password:` on every `cipher.openDatabase`.
Add: `_isUnreadableWithKey` source (comment-stripped IO helper)
contains `open_failed`.

Directory.current is `mobile/`. File reads only. No widgets, no
SQLite open, no `pumpAndSettle`. Do not assert on comments.

No Python. No CREATE TABLE. No backup XML. No Gap 6 wipe changes.

### 4. R17 sabotage

Exact edit: delete the `open_failed` substring from
`_isUnreadableWithKey`.

`test_production_offline_open_passes_sqlcipher_password` must fail.
Restore before the PR. Do not sabotage by deleting the test.
Do not sabotage `password:`.

## Out of scope

- Masking, FLAG_SECURE, iOS file protection, ProGuard
- Hosted 0026, Gap 7, a new APK
- Encrypting Windows FFI / web

## Gates

If Flutter SDK exists:

```
cd mobile
flutter analyze
flutter test
```

If no Flutter SDK: push the Dart files, report that, and stop.
The owner runs Flutter.

R1: after any Dart write, `grep -rn '\\$' mobile/lib` -- only the
two price strings in `upgrade_screen.dart`.

## Report

SHA, branch, files touched. Named test name in the report must be
`test_production_offline_open_passes_sqlcipher_password`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
