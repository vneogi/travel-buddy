# Genie brief: SPEC-43 Gap 11 -- bound request body size and JSON depth

Landed on `main` as `2077d8d` (PR #119). Do not re-implement this slice.
Gap 11 rate landed as `c70296c` (PR #128). Gap 11 spend landed
as `e7c89b5` (PR #131). Remainders: gateway, Play Integrity.
Do not start a `derived_feature` table, hosted 0026, Flutter,
deploy, or an APK without a new brief.

## Goal

Oversized and deeply nested HTTP payloads must fail in middleware
before route handlers, Pydantic, venue search, or the orchestrator
run. Today the only general bound is signal-batch `max_length=100`.
There is no request-body byte cap and no JSON-depth cap.

This is SPEC-43 Gap 11 body/depth bounds only. It is not Cloud
Armor, not per-IP/account rate limits, not LLM spend breakers,
not Play Integrity, not anonymous-account creation control.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 11)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `main.py` (`request_context_middleware`, router includes)
- `routers/signal_router.py` (`SignalBatchRequest` max_length=100)
- `routers/trip_router.py` (`POST /trip/event`)
- `routers/payment_router.py` (Stripe/RevenueCat webhooks -- must
  still accept a normal-sized webhook)

Base branch: latest `main` (`fbe96f6`), including Gap 10
`fbe96f6` (PR #117).

Create and push:

`feat/spec43-g11-abuse`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

A stolen APK or anonymous client can POST a multi-megabyte or
thousand-deep JSON blob. Signal-batch length 100 does not stop
that. Gap 11 acceptance starts with: oversized and deeply nested
payloads fail before expensive parsing or model calls.

Do not build a gateway or spend circuit this slice. Byte cap plus
depth cap is the first bar.

## Current production seams to reuse

- Keep signal-batch `max_length=100`. Do not raise it.
- `GET /health` and other GETs with empty bodies must still 200.
- Auth stays on the route. Middleware must reject oversized/deep
  bodies **before** the route function runs (no user_id required
  for the reject).
- Stripe/RevenueCat webhooks are small JSON. 256 KiB is enough.
  Do not exempt them from the cap.
- Replay the request body for downstream after you read it
  (Starlette `request._receive` / cached body pattern). Do not
  leave handlers with an empty body.
- Public error `detail` is a stable code string, plus
  `request_id` if middleware already set one. No exception text.

No CREATE TABLE. No new pip dependency. No Flutter. No live
Postgres. Do not apply 0026.

## Scope

### 1. Limits

Put named constants in one Python module used by middleware
(e.g. `main.py` or `monitoring/payload_limits.py`):

- `MAX_BODY_BYTES = 262144`  (256 KiB)
- `MAX_JSON_DEPTH = 8`

Depth of a JSON value: dict/list nest one level; scalars are 0.
`{"a": {"b": 1}}` has depth 2.

If `Content-Length` is present and greater than `MAX_BODY_BYTES`,
return **413** without reading the body.

Otherwise read at most `MAX_BODY_BYTES + 1` bytes. If longer,
**413**.

If `Content-Type` is JSON (starts with `application/json`) and
the body is non-empty: `json.loads`, then if depth > 8 return
**400**. Invalid JSON is not this slice (existing 422 path).

Response bodies:

- 413: `{"detail": "payload_too_large", "request_id": ...}`
- 400: `{"detail": "payload_too_deep", "request_id": ...}`

Do not log the payload.

### 2. Named tests

Add `tests/test_spec43_g11_abuse.py`.

`TestClient` only. No widgets. No live Postgres.

Named tests that must exist with these exact names:

`test_oversized_request_body_is_rejected_before_handler`

POST `/api/v1/trip/event` (or `/api/v1/signals`) with a body
larger than `MAX_BODY_BYTES` (Content-Length or raw bytes).
Status 413. `detail` is `payload_too_large`. A module-level
flag or mock on `TripStateMachine.process_event` / signal
ingest must show the handler was **not** called.

`test_deeply_nested_json_is_rejected`

POST JSON whose depth is `MAX_JSON_DEPTH + 1` and whose byte
size is well under the cap. Status 400. `detail` is
`payload_too_deep`. Handler not called.

Also add (any name):

- `GET /health` still 200
- A small valid JSON POST under both caps still reaches a
  handler (401/422 from auth/schema is fine; not 413/400 depth)
- Depth exactly 8 is allowed
- `json.dumps` of the 413/400 body does not include a huge
  payload echo

Do not assert on comments.

### 3. R17 sabotage

Exact edit: skip the byte-size reject (always treat the body as
small enough).

`test_oversized_request_body_is_rejected_before_handler` must
fail. Restore before the PR. Do not sabotage by deleting the
test. Do not sabotage JSON depth.

## Out of scope

- Cloud Run load balancer / Cloud Armor
- Per-IP or per-account request rates
- LLM token/spend circuit breakers
- Play Integrity / App Attest
- Changing signal-batch max_length
- Gap 9 GPS, Gap 7 Flutter, Gap 10 remainders
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

SHA, branch, pytest last line, files touched. Named tests in the
report must include
`test_oversized_request_body_is_rejected_before_handler` and
`test_deeply_nested_json_is_rejected`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.