# Genie brief: SPEC-43 Gap 3 -- redact booking canaries before cache embeddings

Landed on `main` as `b59c50d` (PR #162). Do not re-implement this
slice. Remainders: HEAVY_FALLBACK provider matrix,
`_api_embedding` failure print. Do not enable personal-trip LLM.
Do not start Armor, Play Integrity, SQL cache wiring,
`derived_feature`, hosted 0026, Flutter, deploy, or an APK
without a new brief.

Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43.

## Goal

Outbound redact (`d35895a`) strips booking needles on light
`complete`, `_api_embedding`, and `batch_embeddings`. The
semantic cache still calls
`embedding_service.generate_embedding(query)` with no needles.
A LIGHT Ask that pastes a PNR still ships that PNR to the
embedding provider on every cache check and store.

This is SPEC-43 Gap 3 cache-path embedding redaction only. It
is not changing HMAC cache keys, not synthetic embeddings, not
turning LLM on, not HEAVY_FALLBACK.

Read before editing:

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/cache_service.py` (`check_cache`, `store_response`)
- `services/embedding_service.py` (`generate_embedding`,
  `_api_embedding`)
- `agents/state_machine.py` (`_node_check_cache`,
  `_store_light_response`, `_restricted_needles`)
- `monitoring/redact.py` (`redact_outbound_llm_text`,
  `MIN_RESTRICTED_NEEDLE_LEN`)
- `tests/test_spec43_g3_outbound_redact.py` (must stay green;
  do not weaken)
- `tests/test_spec43_g8_canaries.py` (must stay green; do not
  edit)

Base branch: latest `main` (`fdb6fc7`), including Gap 3 outbound
redact `d35895a` (PR #159).

Create and push: `feat/spec43-g3-cache-embed`

Do not merge. Open one PR after the gates are green.

## Why this exists

Gap 3 acceptance: canary booking codes never appear in
embedding payloads. The cache is the remaining live API-embedding
caller that still sends the raw question.

Do not refuse the request. Redact needles in the string sent to
LiteLLM. Keep `state["message"]` and `hmac_query(query, ...)` on
the original question.

## Current production seams to reuse

- `redact_outbound_llm_text` and `MIN_RESTRICTED_NEEDLE_LEN`
  already exist. Do not invent a second redactor.
- `_api_embedding` already accepts `restricted_needles`.
  `generate_embedding` must forward them when calling
  `_api_embedding`. Synthetic path still hashes the original
  text (do not redact synthetic input).
- `store_response` already has `restricted_needles` for the
  response-is-restricted gate. Pass the same list into
  `generate_embedding`.
- `check_cache` needs a new optional
  `restricted_needles=()` and must pass it to
  `generate_embedding`.
- Orchestrator: `_store_light_response` already has needles;
  `_node_check_cache` must pass `_restricted_needles(state)`
  into `check_cache`.
- Keep spend circuit. Do not log the query or the LiteLLM input.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.
Do not set `TB_LITELLM_API_KEY` in tests.

## Scope

### 1. Thread needles to generate_embedding

`EmbeddingService.generate_embedding(text, user_id=None,
restricted_needles=())`:

- synthetic: unchanged (`_synthetic_embedding(text)` on the
  original text)
- API: `_api_embedding(text, user_id=user_id,
  restricted_needles=restricted_needles)`

### 2. Cache call sites

`check_cache(..., restricted_needles=())` and
`store_response(..., restricted_needles=...)` both call
`generate_embedding(query, restricted_needles=restricted_needles)`
(add `user_id` only if already threaded; do not invent a new
identity path this slice).

`_node_check_cache`: pass
`restricted_needles=self._restricted_needles(state)`.

Do not change HMAC. Do not redact the stored
`response_text`. Do not change identity / trip / date /
source_version matching.

### 3. Named tests

Add `tests/test_spec43_g3_cache_embed.py`. No widgets. No live
Postgres. No real LiteLLM network.

Exact name:

`test_cache_api_embedding_omits_booking_canary`

Monkeypatch `litellm.embedding` to capture `input` and return a
tiny vector. Build a private
`EmbeddingService(use_synthetic=False)` and a private
`SemanticCacheService` that uses it (or monkeypatch the module
singleton the same way existing Gap 8/11 tests do -- pick the
pattern already in-repo).

Call `check_cache` (or `store_response` after a miss path that
embeds) with query
`What time is G3-CANARY-PNR-9f3a at the pier?` and
`restricted_needles=["G3-CANARY-PNR-9f3a"]` plus a usable
identity and ordinary region/venue.

Captured `input` must not contain `G3-CANARY-PNR-9f3a` and must
contain `REDACTED`.

Also (any name):

- `store_response` with the same canary omits it from the
  captured embedding input
- synthetic `generate_embedding` with needles still matches
  `_synthetic_embedding` of the original text
- HMAC of the original query is unchanged (same hex before /
  after this slice for the same key+query)
- outbound-redact named tests stay green

Do not assert on comments.

### 4. R17 sabotage

Exact edit: in `check_cache`, call
`generate_embedding(query)` without
`restricted_needles` (old path).

`test_cache_api_embedding_omits_booking_canary` must fail
(PNR in captured input). Restore before the PR. Do not
sabotage outbound redact, DTO, IAM, or spend.

If Databricks blocks in-place sabotage, an in-memory pytest
plugin that drops needles on the cache `check_cache` embed
call only is the accepted substitute. Named canary must still
fail. Drop the plugin before the PR.

## Out of scope

- Enabling LLM for personal trips
- HEAVY_FALLBACK / provider-region matrix
- Changing HMAC to the redacted query
- Scrubbing `_api_embedding` failure `print`
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

SHA, branch, pytest last line, files touched. Named test in
the report must include
`test_cache_api_embedding_omits_booking_canary`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
