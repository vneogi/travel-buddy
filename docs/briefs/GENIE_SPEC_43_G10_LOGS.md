# Genie brief: SPEC-43 Gap 10 -- redact secrets in the error ring

Landed on `main` as `fbe96f6` (PR #117). Do not re-implement this slice.
Gap 11 spend landed as `e7c89b5` (PR #131). Next: Gap 10 422
stripping (`docs/briefs/GENIE_SPEC_43_G10_422.md`). Remainders:
admin IAM, retention. Do not start hosted 0026, Flutter, deploy,
or an APK without a new brief.

## Goal

Secrets and provider keys must not sit in the in-memory error ring
or the unhandled-exception log line. Hosted Cloud Run must refuse
to start with debug on.

Today `error_log.record` stores `message` and `traceback` raw.
The unhandled handler puts `str(exc)` and the full traceback in
the ring and in `logger.error`. `GET /api/v1/debug/errors` is
gated only on `settings.debug` (no admin IAM). `test_no_secrets
_in_error_log` plants a key on Settings and crashes a route
whose message does not contain that key, so it cannot fail.

This is SPEC-43 Gap 10 redaction + hosted debug refuse only. It
is not a full structured-logging rewrite, not admin IAM on the
debug router, not regional buckets, not changing client 500
bodies (those already omit traceback).

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 10)
- `docs/specs/SPEC-05-observability.md`
- `docs/ENGINEERING_RULES.md` (R12, R14, R17)
- `monitoring/error_log.py`
- `main.py` (`unhandled_exception_handler`, `_lifespan`)
- `routers/debug_router.py`
- `tests/test_observability.py`
- `config/settings.py`

Base branch: latest `main` (`cbe4cf1`), including Gap 8
`62927dd` (PR #114).

Create and push:

`feat/spec43-g10-logs`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

SPEC-05 wanted visible 500s. Gap 10 says those diagnostics must
not retain keys, tokens, or provider URLs. A canary that never
appears in `str(exc)` is not a canary.

Do not build Cloud Logging, retention, or admin SSO this slice.
Redact on write, and refuse debug on Cloud Run, is the first bar.

## Current production seams to reuse

- Client 500 already returns `{"detail": "Internal server error",
  "request_id": ...}` -- keep that.
- Ring still exists. Keep `exc_type`, path, method, status,
  request_id. Redact `message` and `traceback` before append.
- Apply the same redaction to the traceback string passed to
  `logger.error` in the unhandled handler.
- Debug router stays 404 when `settings.debug` is false. Do not
  add admin IAM this slice.
- Pytest sets `TB_DEBUG=true` and clears JWKS. Do not break that.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.

## Scope

### 1. Redact on write

Add `monitoring/redact.py` (name yours) with
`redact_secrets(text: str) -> str`.

Must replace, at least:

- Query `key=` / `api_key=` values
- `Bearer ` tokens
- Literal values of these Settings fields when they are non-empty:
  `litellm_api_key`, `gemini_api_key`, `google_maps_api_key`,
  `google_places_api_key`, `openweather_api_key`, `supabase_key`,
  `supabase_jwt_secret`, `stripe_secret_key`,
  `stripe_webhook_secret`
- Replacement text must be the literal `REDACTED` (so tests can
  assert it). Do not log the original.

Call it inside `ErrorLog.record` on `message` and
`traceback_str` so every writer is covered. Also redact `tb_str`
before `logger.error` in `unhandled_exception_handler`.

Do not store request bodies. Do not start logging Ask prompts.

Keep `test_unhandled_exception_returns_500_with_request_id`:
benign `RuntimeError("Deliberate test crash")` still appears.

### 2. Hosted debug refuse

Add a small function (e.g. `assert_production_debug_off()`)
called at the start of `_lifespan` before `seed_venues`.

If `os.environ.get("K_SERVICE")` is non-empty (Cloud Run sets
this) AND `settings.debug` is True, raise a RuntimeError whose
message says debug is not allowed on Cloud Run. Do not start.

Do not use JWKS-present as the production signal (local `.env`
can have JWKS plus TB_DEBUG). Pytest has no `K_SERVICE`.

### 3. Named tests

Edit `tests/test_observability.py` and/or add
`tests/test_spec43_g10_logs.py`.

Named test that must exist with this exact name:

`test_error_ring_redacts_secret_canary`

`error_log.record` a message and traceback that contain both:

- `sk-test-CANARY-KEY-9f3a`
- `https://maps.googleapis.com/maps/api/foo?key=AIzaSyCanaryKey`

After record, `json.dumps(error_log.recent())` must not contain
either canary string, and must contain `REDACTED`.

Also add (any name):

- Unhandled crash whose `RuntimeError` message is the maps URL
  canary: client JSON has no canary; ring has no canary.
- `assert_production_debug_off` with `K_SERVICE` set and
  `settings.debug True` raises; with `K_SERVICE` unset it does
  not, even if debug is True.
- Existing `test_no_secrets_in_error_log` may stay; do not
  treat it as the Gap 10 canary.

Do not assert on comments. No widgets. No live Postgres.

### 4. R17 sabotage

Exact edit: skip redaction in `ErrorLog.record` (store message
and traceback as passed).

`test_error_ring_redacts_secret_canary` must fail. Restore
before the PR. Do not sabotage by deleting the test. Do not
sabotage the 500 client body or the Cloud Run assert.

## Out of scope

- Admin IAM on `/api/v1/debug/errors`
- Structured log field allowlists for every logger
- Regional buckets, retention, access audit
- Stripping every Pydantic input value from 422 responses
- Gap 11 rate limits, Gap 9 GPS, Gap 7 Flutter
- Hosted 0026, deploy, APK, `pm clear`

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

## Report

SHA, branch, pytest last line, files touched. The named test in
the report must be `test_error_ring_redacts_secret_canary`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.