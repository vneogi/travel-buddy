# Genie brief: Gap 10 IAM part B -- admin header (after part A)

This is the open job. Part A is on `main` as `56ebc00` (PR #148).
Same roles as part A: you implement and open a PR; you do not
merge, deploy, or edit living docs.

## Read (only these)

- `docs/briefs/GENIE_SPEC_43_G10_IAM_A.md` (roles; do not redo A)
- `routers/debug_router.py`
- `config/settings.py` (`debug_admin_token`)
- helper from part A (`admin_token_configured`)
- `security.py` -- first 20 lines (debug user is not admin)
- `tests/test_spec43_g10_iam.py`
- `tests/test_observability.py`
- `tests/conftest.py` (still no `TB_DEBUG_ADMIN_TOKEN`)

## Goal

When the token is configured and debug is on, GET/DELETE
`/api/v1/debug/errors` require header `X-Debug-Admin-Token`
matching `settings.debug_admin_token` via `hmac.compare_digest`
on UTF-8 bytes.

- Missing/wrong header: 401 `{"detail": "Unauthorized"}`, no
  `"errors"`.
- Matching header: existing GET/DELETE bodies.
- `X-Debug-User-Id` and traveller Bearer do not open the ring.
- Debug off: still 404 even with a valid admin token.
- Unset token: keep part A 404.
- Length mismatch: reject without `compare_digest` (it raises).
- Do not log the header or the setting.
- Do not accept query, body, or `Authorization: Bearer` as the
  admin token. Do not add `service_role` to `ALLOWED_ROLES`.
- Do not reuse `supabase_key` or provider keys.

Base branch: latest `main` (`56ebc00`). Branch:
`feat/spec43-g10-iam-b`

## Named tests (exact names)

`test_debug_errors_requires_admin_token`

Debug True, token `g10-admin-canary-token`. GET no header: 401,
no `"errors"`. GET with that header: 200 with `"errors"`. GET
with `wrong-token-not-the-canary`: 401.

`test_debug_errors_rejects_debug_user_header`

Same token. GET with only `X-Debug-User-Id: user-g10-iam`: 401.

Also: DELETE uses the same gate; debug False + valid token is
404; part A unset tests stay green.

Update `test_debug_errors_returns_200_when_debug_on` to
monkeypatch the 22-char token and send the header.

Do not set the env var in `conftest.py`.

## R17

Skip the header check when debug is True (old dump).

`test_debug_errors_requires_admin_token` must fail (bare GET
200 with `"errors"`). Restore before the PR. Do not sabotage
part A unset 404, redaction, or Cloud Run refuse.

## Gates / report

Same gates as part A. Named tests in the report: both names
above. Do not merge. Do not edit living docs or this brief.
Do not "fix" `test_today_tonight_includes_venue_name`.
