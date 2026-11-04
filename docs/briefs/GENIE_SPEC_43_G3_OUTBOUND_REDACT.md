# Genie brief: SPEC-43 Gap 3 -- redact booking canaries before light complete and embeddings

Landed on `main` as `d35895a` (PR #159). Do not re-implement this
slice. Remainders: HEAVY_FALLBACK provider matrix, cache-path
embedding of the raw query, `_api_embedding` failure print.
Do not enable personal-trip LLM. Do not start Armor, Play
Integrity, SQL cache, `derived_feature`, hosted 0026, Flutter,
deploy, or an APK without a new brief.

Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43. Do not enable personal-trip LLM. Do not start
HEAVY_FALLBACK / provider-region matrix, Armor, Play Integrity,
SQL cache, `derived_feature`, hosted 0026, Flutter, deploy, or
an APK.

## Goal

The heavy itinerary DTO (`dd0e6d3`) strips node fields. It does
not touch the traveller's question. `generate_info_response`
sends `user_message` raw. `embedding_service._api_embedding` and
`LLMService.batch_embeddings` send the query raw to LiteLLM.
A pasted PNR in Ask or LIGHT phrasing still leaves the process.

This is SPEC-43 Gap 3 outbound text redaction on the light
complete path and the API embedding path. It is not turning LLM
on, not killing fallback, not synthetic embeddings.

Read before editing:

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/llm_service.py` (`generate_info_response`,
  `generate_itinerary_response` user_message line,
  `batch_embeddings`)
- `services/embedding_service.py` (`_api_embedding`)
- `agents/state_machine.py` (`_store_light_response` needles,
  `_node_generate_response` light call)
- `monitoring/redact.py` (`redact_secrets`, `REDACTED`)
- `services/cache_service.py` (`MIN_RESTRICTED_NEEDLE_LEN` --
  reuse 6-char floor; do not change HMAC)

Base branch: latest `main` (`7f4ccc1`), including Gap 3 DTO
`dd0e6d3` (PR #156).

Create and push: `feat/spec43-g3-outbound-redact`

Do not merge. Open one PR after the gates are green.

## Why this exists

Gap 3 acceptance: canary booking codes never appear in
completion or embedding payloads. Allowlisting node keys does
not cover the question string.

Do not refuse the request. Replace needles with the literal
`REDACTED` in the string sent to LiteLLM. The orchestrator may
keep the original `state["message"]` for cache keys.

## Current production seams to reuse

- `redact_secrets` first (keys, Bearer, sk-, AIza).
- Extra needles: same rule as Gap 8 -- string, strip, length
  >= 6 (`MIN_RESTRICTED_NEEDLE_LEN` or a shared constant).
  Replace every occurrence with `REDACTED`. Longest first.
- Keep spend circuit. Synthetic embeddings (`use_synthetic=True`)
  are local hashes, not a provider payload; do not redact them
  (would change vectors). Only `_api_embedding` and
  `aembedding` inputs.
- Keep `user_id` as spend identity, not prompt text.
- Do not log the original question or the LiteLLM input.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.
Do not set `TB_LITELLM_API_KEY` in tests.

## Scope

### 1. Helper

Add `redact_outbound_llm_text(text: str, extra_needles=()) -> str`
(in `monitoring/redact.py` or `services/llm_public.py`).

Order: `redact_secrets`, then extra needles (len >= 6 after
strip). Return the redacted string. Empty text stays empty.

### 2. Call sites

- `generate_info_response`: add `restricted_needles=()`. Build
  `user_block` as today, then
  `redact_outbound_llm_text(user_block, restricted_needles)`
  before `messages`.
- `generate_itinerary_response`: collect needles from each
  node dict's `confirmation_code` and `booking_notes`. Redact
  the `User request:` line (the `user_message`) with those
  needles. Do not undo the node DTO allowlist.
- `_api_embedding`: redact `text` with optional
  `restricted_needles=()` before `litellm.embedding`.
- `batch_embeddings`: redact each string the same way before
  `litellm.aembedding`.
- `state_machine._node_generate_response` light call: pass the
  same needle list `_store_light_response` already builds.

Do not change `HEAVY_FALLBACK`. Do not change HMAC cache keys
to use the redacted question.

### 3. Named tests

Add `tests/test_spec43_g3_outbound_redact.py`. No widgets. No
live Postgres. No real LiteLLM network.

Exact names:

`test_info_llm_payload_omits_booking_canary`

Monkeypatch `LLMService.complete` to capture `messages`. Call
`generate_info_response` with user_message
`What time is G3-CANARY-PNR-9f3a at the pier?` and
`restricted_needles=["G3-CANARY-PNR-9f3a"]`. Captured JSON must
not contain `G3-CANARY-PNR-9f3a` and must contain `REDACTED`.

`test_api_embedding_input_omits_booking_canary`

Monkeypatch `litellm.embedding` to capture `input`.
`EmbeddingService(use_synthetic=False)._api_embedding` with
text containing `G3-CANARY-PNR-9f3a` and
`restricted_needles=["G3-CANARY-PNR-9f3a"]` (return a tiny
fake vector). Captured `input` must not contain the canary
and must contain `REDACTED`.

Also (any name): `generate_itinerary_response` with the canary
in `user_message` and on the node `confirmation_code` omits it
from captured `complete` messages; DTO venue name still present.
Needles shorter than 6 chars are not replaced. Helper-only tests
are not the canary.

Do not assert on comments.

### 4. R17 sabotage

Exact edit: in `generate_info_response`, skip
`redact_outbound_llm_text` (send `user_block` raw).

`test_info_llm_payload_omits_booking_canary` must fail (PNR in
captured messages). Restore before the PR. Do not sabotage the
itinerary DTO, spend, or IAM.

If Databricks blocks in-place sabotage, an in-memory pytest
plugin that skips info-path redaction only is the accepted
substitute. Named canary must still fail. Drop the plugin
before the PR.

## Out of scope

- Enabling LLM for personal trips
- HEAVY_FALLBACK / provider-region matrix
- Redacting synthetic embeddings
- Changing semantic-cache HMAC to the redacted query
- Armor, Play Integrity, Flutter, deploy, APK, 0026

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.
Do not "fix" `test_today_tonight_includes_venue_name` or
`test_sparse_create_with_limited_hours_succeeds`.

## Report

SHA, branch, pytest last line, files touched. Named tests in
the report must include
`test_info_llm_payload_omits_booking_canary` and
`test_api_embedding_input_omits_booking_canary`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
