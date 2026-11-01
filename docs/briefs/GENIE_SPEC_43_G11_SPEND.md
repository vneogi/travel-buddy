# Genie brief: SPEC-43 Gap 11 -- in-process provider-spend circuit

This is the open Gap 11 spend first slice. Implement it. Do not start
Cloud Armor, Play Integrity, a `derived_feature` table, hosted 0026,
Flutter, deploy, an APK, or production LLM processing of personal
trip data.

## Goal

`LLMService.complete` will call every model in the fallback chain
until LiteLLM fails. `_total_cost` is a running sum with no cap.
`embedding_service._api_embedding` calls `litellm.embedding` with
no budget. Rate limits stop request floods. They do not stop one
Ask from burning provider dollars, and a new identity does not
reset a process-wide dollar cap.

This is SPEC-43 Gap 11 in-process spend circuit only. It is not a
load-balancer, not Play Integrity, not Maps/Weather quotas, not
AskBudget (Ask counts, not USD), not turning LLM on for personal
trips.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 11)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `services/llm_service.py` (`complete`, fallback `except Exception`,
  `stream_response`, `batch_embeddings`, `_calculate_cost`)
- `services/embedding_service.py` (`_api_embedding`)
- `services/ask_service.py` (`AskBudget` -- do not reuse as USD)
- `monitoring/rate_limit.py` (constructor-override pattern)

Base branch: latest `main` (`a4ee6c9`), including Gap 11 rate
`c70296c` (PR #128).

Create and push:

`feat/spec43-g11-spend`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 11 acceptance includes: load tests cannot exceed the configured
downstream spend budget, and UUID rotation does not bypass all
limits. Reroute daily count and AskBudget fail that bar. Count
USD in process memory before LiteLLM is invoked.

Do not put Cloud Armor or billing webhooks in this slice.
In-memory on one Cloud Run instance is the first bar.

## Current production seams to reuse

- New module e.g. `monitoring/spend_circuit.py`. Constructor
  overrides for tests (same idea as `RateLimitMiddleware`).
- Gate **before** `litellm.acompletion`, `litellm.embedding`,
  `litellm.aembedding`, and the stream `acompletion`. Synthetic
  embeddings (`use_synthetic=True`) are not spend; do not count
  them and do not call LiteLLM.
- Identity key: `user_id` already on orchestrator state. Thread
  it into `complete` / generate helpers as `user_id` (stripped,
  lowercased). Empty or missing becomes `anonymous`.
- Process key: one bucket for the whole process (rotation bar).
- If **either** process or identity bucket would exceed the cap,
  do not call LiteLLM.
- `complete`'s fallback loop currently `except Exception: continue`.
  A spend reject **must not** be swallowed and retried on the next
  model. Re-raise (or return) immediately. This is the R17 trap.
- Do not enable personal-trip LLM. Do not change the deterministic
  Ask router. Do not log prompts, Authorization, or API keys.
- Keep rate-limit and body/depth middleware. Do not weaken them.
- Keep `AskBudget` as Ask counts. Do not fold USD into it.

No CREATE TABLE. No new pip dependency. No Redis. No Flutter.
No live Postgres. Do not apply 0026. Do not wrap Google Maps,
OpenWeather, Stripe, or Supabase HTTP.

## Scope

### 1. Circuit

Named constants in the spend module:

- `SPEND_WINDOW_S = 86400`
- `MAX_PROCESS_USD = 5.0`
- `MAX_IDENTITY_USD = 1.0`

`SpendCircuit(max_process_usd=..., max_identity_usd=..., window_s=...)`.
Defaults are the named constants.

Sliding window of `(timestamp, usd)` per key. Drop entries older
than the window. Reject when `sum(remaining) + reserved >= max`.

`allow(identity, reserved_usd) -> bool` does not mutate. `record`
appends after a successful provider response. Pre-check with a
reserved amount from `_calculate_cost` using prompt size and
`max_tokens` (or a documented embedding estimate) so a large
completion cannot sneak through. After success, `record` the
actual `cost_usd`. Do not double-count reserved plus actual.

Process bucket and identity bucket are independent. Either over
cap is a reject.

Module-level default circuit used by `llm_service` and
`embedding_service`. `LLMService.__init__` must accept an
optional circuit so named tests can inject a private one.
Do not lower the installed default in pytest autouse; private
instances only, like Gap 11 rate spies.

Public reject signal: a dedicated exception type (e.g.
`SpendCapped`) with a stable `detail` string `spend_capped`.
Do not put USD figures, model names, or prompts on that
exception message.

### 2. Call sites

`LLMService.complete`: allow, then LiteLLM, then record. Spend
reject skips the fallback chain.

`stream_response` and `batch_embeddings`: same allow-before-call.

`EmbeddingService._api_embedding`: allow before `litellm.embedding`.
On spend reject, do **not** fall back to synthetic (that mixes
embedding spaces while a live key is configured). Raise
`SpendCapped`.

Pass `user_id` from orchestrator LLM call sites that already
have `state["user_id"]`. Helpers that have no identity use
`anonymous` (still counts against the process bucket).

### 3. Named tests

Add `tests/test_spec43_g11_spend.py`.

No widgets. No live Postgres. No real LiteLLM network. Stub
`litellm.acompletion` / `litellm.embedding` with a tiny usage
payload (`prompt_tokens` / `completion_tokens` known so cost is
deterministic via `_calculate_cost`).

Named tests that must exist with these exact names:

`test_excess_spend_from_one_identity_is_capped`

Private `SpendCircuit` (max_identity_usd small, max_process_usd
huge, window_s=86400) injected into a private `LLMService`.
Stub `acompletion` so each success costs a known USD. After the
identity is at/over the identity cap, the next `complete` does
not call LiteLLM, raises `SpendCapped` (or returns without a
provider call -- pick one and assert the stub call count). Stub
called N times not N+1.

`test_spend_circuit_is_not_bypassed_by_new_identity`

Private circuit (max_process_usd small, max_identity_usd huge).
Two (or more) different `user_id` values. After the process
bucket is exhausted, a new identity still does not call
LiteLLM. This is the rotation bar.

Also add (any name):

- synthetic embedding path does not call LiteLLM and does not
  record spend
- `complete` fallback does not skip to the next model on
  `SpendCapped` (stub first model so cost records; trip the
  cap; assert second model never called)
- reject does not include prompt text, API keys, or USD in the
  public `detail`

Do not assert on comments.

### 4. R17 sabotage

Exact edit: skip the process bucket (always treat process sum
as under the cap). Keep the identity bucket.

`test_spend_circuit_is_not_bypassed_by_new_identity` must fail
(new identity still reaches LiteLLM because identity caps are
huge). Restore before the PR. Do not sabotage by deleting the
test. Do not sabotage the identity bucket.

## Out of scope

- Cloud Armor / load balancer
- Play Integrity / App Attest
- Maps, OpenWeather, Stripe, RevenueCat spend
- Changing `AskBudget` or daily reroute quota
- Enabling production LLM on personal trips
- Billing dashboards, LiteLLM proxy, Redis
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
`test_excess_spend_from_one_identity_is_capped` and
`test_spend_circuit_is_not_bypassed_by_new_identity`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
