# Genie brief: SPEC-43 Gap 11 -- per-identity and per-IP request rate

Landed on `main` as `c70296c` (PR #128). Do not re-implement this slice.
Remainders: gateway/Cloud Armor, spend circuit, Play Integrity.
`derived_feature` table stays later. Do not start hosted 0026,
Flutter, deploy, or an APK without a new brief. No open Genie brief.

## Goal

A stolen APK or rotating debug/anonymous identity can POST
`/api/v1/trip/event` as fast as Cloud Run will accept. Body/depth
caps stop megabyte payloads. They do not stop a flood of small
orchestrator calls. Reroute quota is daily and per user_id after
auth; it does not cover Ask or other events, and a new identity
resets it.

This is SPEC-43 Gap 11 in-process rate limits only. It is not a
load-balancer, not spend, not Play Integrity, not anonymous JWT
minting control.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 11)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `main.py` (`PayloadLimitMiddleware`, `request_context_middleware`)
- `monitoring/payload_limits.py` (ASGI reject + request_id pattern)
- `routers/trip_router.py` (`POST /trip/event`)
- `routers/payment_router.py` (Stripe/RevenueCat webhooks)

Base branch: latest `main` (`c87b398`), including Gap 9 derived
metadata `4265403` (PR #125).

Create and push:

`feat/spec43-g11-rate`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 11 acceptance includes: UUID/account rotation does not bypass
all limits. Per-user reroute quota fails that bar. Count both an
identity key and a client IP in process memory, before the
orchestrator.

Do not put Cloud Armor in this slice. In-memory on one Cloud Run
instance is the first bar.

## Current production seams to reuse

- Register ASGI middleware next to `PayloadLimitMiddleware`.
  `request_context_middleware` stays outermost so 429 includes
  `request_id` / `X-Request-ID`.
- Limit `POST`, `PUT`, `PATCH`, `DELETE` only.
- Exempt (no count, never 429 from this limiter):
  - `GET /api/v1/health` (and other GETs)
  - `POST /api/v1/payment/webhook/stripe`
  - `POST /api/v1/payment/webhook/revenuecat`
- Identity key, do not verify JWT:
  1. `X-Debug-User-Id` if present (stripped, lowercased)
  2. else SHA-256 hex of the raw `Authorization` header, first 16
     chars (do not log the header)
  3. else `anonymous`
- IP key: ASGI `client` host, or `unknown`.
- If either bucket is over the cap, return **429** without calling
  the app. Public body:
  `{"detail": "rate_limited", "request_id": ...}`
- Do not log Authorization, debug user ids, or payloads.
- Keep reroute daily quota. Do not change it.
- Keep body/depth middleware. Do not weaken it.

No CREATE TABLE. No new pip dependency (no slowapi). No Redis.
No Flutter. No live Postgres. Do not apply 0026.

## Scope

### 1. Limits

Put named constants in one module (e.g. `monitoring/rate_limit.py`):

- `RATE_WINDOW_S = 60`
- `MAX_REQUESTS_PER_IDENTITY = 30`
- `MAX_REQUESTS_PER_IP = 60`

Constructor must accept overrides so tests can use identity=3,
ip=8, window=60 without a 30-request flood in CI.

Sliding window: store timestamps per key; drop entries older than
the window; reject when the remaining count is >= max.

`RateLimitMiddleware(app, max_identity=..., max_ip=..., window_s=...)`.

Default constructor values are the named constants. `main.py`
registers `app.add_middleware(RateLimitMiddleware)` with defaults.

Tests that need small caps should build a private
`RateLimitMiddleware` with an inner spy, like
`test_declared_content_length_over_cap_is_rejected` in Gap 11, OR
monkeypatch the constants before importing the app. Prefer a
private ASGI inner for the named tests so the shared `TestClient`
app is not poisoned.

### 2. Named tests

Add `tests/test_spec43_g11_rate.py`.

No widgets. No live Postgres.

Named tests that must exist with these exact names:

`test_excess_requests_from_one_identity_are_rate_limited`

Drive a private `RateLimitMiddleware` (max_identity=3, max_ip=100,
window_s=60) with ASGI scope `X-Debug-User-Id: user-rate` and
`client: ('1.1.1.1', 0)`, POST `/api/v1/trip/event`. The 4th
request is 429, `detail` is `rate_limited`, inner app called 3
times not 4.

`test_rate_limit_is_not_bypassed_by_new_debug_identity`

Same middleware (max_identity=100, max_ip=3, window_s=60). Four
POSTs from the same IP `2.2.2.2` with four different
`X-Debug-User-Id` values. The 4th is 429. Inner app called 3
times. This is the rotation bar.

Also add (any name):

- GET `/api/v1/health` on the real `TestClient(app)` still 200
  after several GETs
- Stripe webhook path is not counted (private middleware, 5 POSTs
  to `/api/v1/payment/webhook/stripe` with max_ip=3 still reach
  inner)
- 429 JSON does not echo Authorization or the debug user id
- 429 includes `request_id` when scope.state has one

Do not assert on comments.

### 3. R17 sabotage

Exact edit: skip the identity bucket (always treat identity count
as under the cap). Keep the IP bucket.

`test_excess_requests_from_one_identity_are_rate_limited` must
fail (4th request reaches inner / not 429, because max_ip=100).
Restore before the PR. Do not sabotage by deleting the test. Do
not sabotage the IP bucket.

## Out of scope

- Cloud Armor / load balancer
- Redis / global multi-instance counters
- LLM spend circuit breakers
- Play Integrity / App Attest
- Rate-limiting webhooks
- Changing daily reroute quota
- `derived_feature` table
- Gap 7 Flutter, Gap 8 HMAC, Gap 10 IAM
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
`test_excess_requests_from_one_identity_are_rate_limited` and
`test_rate_limit_is_not_bypassed_by_new_debug_identity`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.