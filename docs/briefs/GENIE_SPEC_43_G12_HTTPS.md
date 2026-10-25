# Genie brief: SPEC-43 Gap 12 -- release HTTPS fail-closed

Landed on `main` as `6f1dab8` (PR #82). Do not re-implement this slice.
Cache keys `290f821`. Chat URLs `14ce56d`. Next:
`docs/briefs/GENIE_SPEC_43_G12_ATS.md`.

## Goal

A release build must not talk to the API or Supabase over HTTP.

`Env.apiBaseUrl` defaults to `http://10.0.2.2:8000`. Release code does
not refuse that. A mis-defined APK can ship cleartext.

This is SPEC-43 Gap 12 HTTPS only. It is not cache identity keys, chat
query strings, deep links, Android network-security XML, iOS ATS, Gap 5
SQLCipher, Gap 11, deploy, or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 12)
- `mobile/lib/core/env.dart`
- `mobile/lib/main.dart`
- `mobile/lib/core/api_client.dart`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including Gap 9 `163a14c` (PR #81).

Create and push:

`feat/spec43-g12-https`

Do not merge. Open one PR only after the gates below are green.

## Scope

### 1. HTTPS check

Add one function (name yours) that, in release, refuses:

- `Env.apiBaseUrl` if the scheme is not `https`
- `Env.supabaseUrl` when non-empty if the scheme is not `https`

Debug/profile keep the emulator HTTP default. Do not change the debug
default to HTTPS.

Call it from `main()` before `runApp` (after bindings). On failure:
throw / fail startup. Do not silently rewrite http to https.

Empty `supabaseUrl` in debug is still allowed (tests). Empty supabase
in release: fail (auth cannot be HTTP-less and also missing).

Do not add a new dart-define except if you need an explicit test hook
for "treat as release" -- prefer a parameter `bool release` defaulting
to `kReleaseMode` so tests can pass `release: true` without a real
release build.

### 2. Tests

`mobile/test/spec43_g12_https_test.dart`.

No live network. No `pumpAndSettle`. No `physicalSize`. Unique
in-memory db not required if you do not open SQLite.

Must include named test:

`test_release_http_api_base_url_is_rejected`

That test fails unless release+HTTP throws. Also: release+https
succeeds; debug+http emulator default succeeds.

R1: after Dart writes, `grep -rn '\$' mobile/lib` still only the two
`upgrade_screen.dart` price strings.

### 3. R17 sabotage

1. Temporarily skip the release HTTP reject (always return ok).
2. Run `test_release_http_api_base_url_is_rejected`.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

## Non-goals

- identity-scoped `cache_trip` / `cache_place` (later Gap 12)
- chat text in route URLs
- deep-link ownership
- network_security_config.xml / ATS plist
- Gap 5, Gap 10, Gap 11
- hosted deploy, APK, applying 0026

## Gates

```bash
ruff check .
ruff format --check .
pytest -q -ra --strict-markers
git diff --check
```

Flutter (say so if the SDK is absent):

```bash
flutter analyze --no-fatal-infos
flutter test test/spec43_g12_https_test.dart
```
