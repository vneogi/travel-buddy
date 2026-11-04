# Genie brief: SPEC-43 Gap 10 -- administrator IAM on the debug ring

This is the open job. Do not start log retention, Armor, Play
Integrity, a `derived_feature` table, Gap 8 SQL cache wiring,
hosted 0026, Flutter, deploy, or an APK.

## Goal

`GET` and `DELETE /api/v1/debug/errors` are gated only on
`settings.debug`. Pytest and local processes set `TB_DEBUG=true`.
Anyone who can hit that process -- USB tunnel, LAN, a leaked
port -- can dump or clear the ring with no extra secret.
`X-Debug-User-Id` is a traveller identity, not an administrator.

Hosted Cloud Run already refuses to start with debug on
(`K_SERVICE`). This slice is the remaining hole: diagnostics
must stay unreachable without administrator authorization even
when debug is on.

This is SPEC-43 Gap 10 admin IAM on the debug router only. It is
not SSO, not Cloud Logging, not retention, not a second ring.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 10)
- `docs/specs/SPEC-05-observability.md` (security note: ring was
  debug-only with no token)
- `docs/ENGINEERING_RULES.md` (R14, R17)
- `routers/debug_router.py`
- `config/settings.py`
- `security.py` (do not treat debug user as admin)
- `tests/test_observability.py`
- `tests/test_spec43_g10_logs.py`
- `tests/conftest.py` (`TB_DEBUG=true`)

Base branch: latest `main` (`c7b9b5a`), including Gap 8 purge
`8fab43b` (PR #145) and the purge living-docs record
`c7b9b5a` (PR #146).

Create and push:

`feat/spec43-g10-iam`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 10 acceptance: debug diagnostics are unreachable without
administrator authorization. SPEC-05 originally allowed an
unauthenticated ring on debug. SPEC-43 retracts that before any
non-owner tester.

A shared admin token is the IAM for this slice. Do not build
Google SSO, Supabase dashboard login, or a new JWT role.

## Current production seams to reuse

- Keep 404 when `settings.debug` is false, even if the caller
  sends a valid admin token. Production must not advertise the
  route.
- Keep ring redaction, Cloud Run debug refuse, and 422 stripping.
- Keep `X-Debug-User-Id` as the pytest traveller identity. It
  must not open `/debug/errors`.
- Keep traveller Bearer / JWKS as they are. `role=authenticated`
  is not administrator. Do not add `service_role` to
  `ALLOWED_ROLES` to unlock the ring.
- Do not reuse `supabase_key`, `supabase_jwt_secret`, or any
  provider API key as the admin token.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.

## Scope

### 1. Admin token setting

Add `debug_admin_token: Optional[str] = None` on Settings
(`TB_DEBUG_ADMIN_TOKEN`). Default empty/unset.

Treat the token as unset when it is None, empty, or shorter than
16 characters. Unset is fail-closed: `/debug/errors` GET and
DELETE return 404 even if `settings.debug` is True.

Document an empty `TB_DEBUG_ADMIN_TOKEN=` in `.env.example` with
a one-line comment: required to read the debug ring; never ship
it on Cloud Run.

Do not commit a real token.

### 2. Gate both debug routes

In `debug_router.py`, after the debug-off 404:

- Read header `X-Debug-Admin-Token` (that exact name).
- Do not accept the token as a query parameter, JSON body, or
  `Authorization: Bearer` (Bearer is traveller auth).
- Compare with `hmac.compare_digest` on UTF-8 bytes. If the
  provided header length differs from the configured token,
  reject without calling `compare_digest` (it raises on length
  mismatch). Do not log the header or the setting.
- Wrong or missing token while debug is on and the setting is
  configured: 401 with `{"detail": "Unauthorized"}`. Do not
  return ring JSON.
- Matching token while debug is on: existing GET/DELETE
  behaviour.

Apply the same helper to GET `/errors` and DELETE `/errors`.

Do not change `error_log.record` or `redact_secrets`.

### 3. Named tests

Add `tests/test_spec43_g10_iam.py`.

No widgets. No live Postgres.

Named tests that must exist with these exact names:

`test_debug_errors_requires_admin_token`

Monkeypatch `settings.debug` True and
`settings.debug_admin_token` to the literal
`g10-admin-canary-token` (that exact 22-character string).
`GET /api/v1/debug/errors` with no admin header is 401 and the
body JSON has no `"errors"` key. Same URL with
`X-Debug-Admin-Token: g10-admin-canary-token` is 200 and has
`"errors"`. `X-Debug-Admin-Token: wrong-token-not-the-canary`
is 401.

`test_debug_errors_rejects_debug_user_header`

Same monkeypatch. `GET /api/v1/debug/errors` with
`X-Debug-User-Id: user-g10-iam` and no admin token is 401.
That header plus a traveller `Authorization` value, if you send
one, still 401 unless `X-Debug-Admin-Token` matches.

Also add (any name):

- debug False + valid admin token -> 404, no `"errors"`
- debug True + unset/empty/short token (`x` * 8) -> 404 even
  with that short value sent as the header
- DELETE `/api/v1/debug/errors` uses the same gate as GET
- existing `test_error_ring_redacts_secret_canary` stays green

Update `test_debug_errors_returns_200_when_debug_on` in
`tests/test_observability.py` so it monkeypatches the same
22-character token and sends `X-Debug-Admin-Token`. Do not
leave a 200 assertion on a bare GET. Keep
`test_debug_errors_returns_404_when_debug_off`.

Do not set `TB_DEBUG_ADMIN_TOKEN` in `tests/conftest.py`.
Fail-closed default in pytest is the point.

Do not assert on comments.

### 4. R17 sabotage

Exact edit: in the debug router, skip the admin-token check when
`settings.debug` is True (old unauthenticated dump).

`test_debug_errors_requires_admin_token` must fail (bare GET
returns 200 with `"errors"`). Restore before the PR. Do not
sabotage by deleting the test. Do not sabotage redaction, 422
stripping, or the Cloud Run debug refuse.

## Out of scope

- Log-bucket retention, regional buckets, access audit
- Structured field allowlists for every logger
- Armor, Play Integrity, LLM gateway
- `derived_feature`, hosted 0026
- Flutter, deploy, APK
- Changing `X-Debug-User-Id` for ordinary pytest routes

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

Do not "fix" `test_today_tonight_includes_venue_name`.

## Report

SHA, branch, pytest last line, files touched. Named tests in the
report must include `test_debug_errors_requires_admin_token` and
`test_debug_errors_rejects_debug_user_header`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
