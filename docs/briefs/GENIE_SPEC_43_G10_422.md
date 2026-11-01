# Genie brief: SPEC-43 Gap 10 -- strip values from client 422 bodies

Landed on `main` as `04169f9` (PR #134). Do not re-implement this slice.
Remainders: admin IAM, log retention. `derived_feature` table stays
later. Do not start hosted 0026, Flutter, deploy, or an APK without
a new brief. No open Genie brief.

## Goal

Pydantic `RequestValidationError` currently returns `exc.errors()` to
the client. Those dicts include `input` (the raw field value) and
often `ctx`. A traveller who pastes a booking code or token into the
wrong field gets that value echoed on a 422. The ring and the
validation `logger.warning` store the same dicts.

500s already return only `Internal server error` plus `request_id`.
Ring redaction already replaces configured secrets. This slice is
the remaining user-facing 422 leak.

This is SPEC-43 Gap 10 client 422 value stripping only. It is not
admin IAM on `/debug/errors`, not log-bucket retention, not rewriting
router `HTTPException` 422s that already use typed `error` codes.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 10)
- `docs/specs/SPEC-05-observability.md` (validation values are not
  log fields)
- `docs/ENGINEERING_RULES.md` (R14, R17)
- `main.py` (`validation_exception_handler`)
- `monitoring/redact.py`
- `tests/test_observability.py` (`test_validation_error_returns_422`)
- `tests/test_spec40_guided_create.py` (`TestMalformedInterests`,
  `test_event_validation_stays_generic`)

Base branch: latest `main` (`8262a23`), including Gap 11 spend
`e7c89b5` (PR #131).

Create and push:

`feat/spec43-g10-422`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 10 acceptance: user-facing errors contain no upstream body, URL,
key, or traceback. FastAPI's default 422 `input` field is the body.

Do not put administrator SSO on the debug router this slice.
Strip validation values on the way out is the first bar.

## Current production seams to reuse

- Keep `validation_exception_handler`. Do not delete the SPEC-40
  create mapping for `invalid_interests` / `invalid_date`.
- Public 422 body shape stays `{detail, request_id}`.
- Generic (non-create) detail stays a **list** of error dicts, so
  `test_event_validation_stays_generic` still passes. Each dict may
  keep only `type`, `loc`, `msg`. Drop `input`, `ctx`, `url`, and
  any other key.
- Typed create 422 stays a dict with `error` plus a short `message`
  that does not contain the rejected value (`err.get("msg")` is the
  Pydantic message, not `input` -- keep that).
- Record the **stripped** error list in `error_log.record` and in
  the validation `logger.warning`. Do not log `exc.errors()` raw.
- 500 handler, spend 503, and rate 429 stay as they are.
- `redact_secrets` stays for keys in the 500 path. Do not fold 422
  stripping into that function; stripping is a key allowlist, not
  secret-literal replacement.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.
Do not change router `HTTPException(status_code=422, ...)` copies
that already return `{error: "<code>", ...}`.

## Scope

### 1. Strip helper

Add a small helper (e.g. `monitoring/validation_public.py`) with
something like `public_validation_errors(errors) -> list[dict]`.

For each error dict, emit only:

- `type` (string)
- `loc` (tuple/list of path segments, JSON-serializable)
- `msg` (string)

If a value is missing, omit the key. Do not copy `input`. Do not
copy `ctx`. Do not copy `url`.

Use that helper for:

- the generic 422 `detail` list
- `error_log.record(..., message=...)`
- the validation `logger.warning` interpolation

### 2. Named tests

Add `tests/test_spec43_g10_422.py`.

No widgets. No live Postgres.

Named tests that must exist with these exact names:

`test_422_does_not_echo_request_values`

`POST /api/v1/trip/event` as a debug user with JSON that fails
Pydantic (wrong types / missing fields) and a unique canary in a
field value, e.g. `trip_id` as integer `12345` plus
`message: "sk-CANARY-g10-422-do-not-echo"`. Response is 422.
The response **text** (full body) must not contain
`sk-CANARY-g10-422-do-not-echo`. `detail` is a list. No error
dict has an `input`, `ctx`, or `url` key. `request_id` is present.

`test_422_create_invalid_interests_stays_typed`

`POST /api/v1/trip/create` with `preferences.interest_ids` set to
a string (same idea as `test_string_interest_ids_returns_typed_422`).
Still 422 with `detail.error == "invalid_interests"`. The body
must not contain that string value if you plant a canary as the
string.

Also add (any name):

- generic 422 still records a ring entry with
  `exc_type == "RequestValidationError"` and `status == 422`, and
  the ring `message` does not contain the canary
- existing `test_event_validation_stays_generic` remains green
  (do not change that test)

Do not assert on comments.

### 3. R17 sabotage

Exact edit: in the generic (non-create) 422 return, pass
`exc.errors()` into `detail` instead of the stripped list. Keep
the typed create mapping.

`test_422_does_not_echo_request_values` must fail (canary appears
in the body / `input` key present). Restore before the PR. Do not
sabotage by deleting the test. Do not sabotage the create mapping.

## Out of scope

- Admin IAM on `/api/v1/debug/errors`
- Log retention / regional buckets
- Rewriting trip-router HTTPException 422 codes
- 500 body (already opaque)
- Rate 429 / spend 503
- Armor, Play Integrity, `derived_feature`, hosted 0026
- Flutter, deploy, APK

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

Do not freeze wall-clock "today" against ICT midnight (the
`test_today_tonight_includes_venue_name` flake is unrelated; do
not "fix" it in this PR).

## Report

SHA, branch, pytest last line, files touched. Named tests in the
report must include
`test_422_does_not_echo_request_values` and
`test_422_create_invalid_interests_stays_typed`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
