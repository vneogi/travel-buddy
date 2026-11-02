# Genie brief: SPEC-43 Gap 8 -- HMAC the in-memory cache query

Landed on `main` as `5a9f684` (PR #137). Do not re-implement this slice.
Next: Gap 8 restricted-content canaries
(`docs/briefs/GENIE_SPEC_43_G8_CANARIES.md`). Remainders:
trip/date/source-version, active purge, unused Supabase cache path.
Do not start hosted 0026, Flutter, deploy, or an APK without a
new brief.

## Goal

Identity-scoped cache entries still keep the raw question in
`CacheEntry.query_text`. A dump of the process cache, a debug
ring, or a log of the entry is the traveller's question.

Hits already use cosine on an embedding computed at request time.
The stored string is not needed for matching.

This is SPEC-43 Gap 8 HMAC-of-query on the live in-memory cache
only. It is not canaries, not trip/date hashing, not a sweeper,
not wiring `supabase_service.check_cache` / `store_cache`.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 8)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `services/cache_service.py` (`CacheEntry.query_text`,
  `check_cache`, `store_response`)
- `tests/test_spec43_g8_cache.py`
- `agents/state_machine.py` (`_node_check_cache`)
- `services/supabase_service.py` (`store_cache` -- unused on the
  live path; do not wire)

Base branch: latest `main` (`f80e4a3`), including Gap 10 422
`04169f9` (PR #134).

Create and push:

`feat/spec43-g8-hmac`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 8 acceptance includes storing an HMAC or normalized intent
key instead of raw question text. Identity isolation already
stops cross-user hits. It does not stop the question sitting in
process memory as plaintext.

Do not add trip/date/source-version to the key this slice.
HMAC the query string is the first bar.

## Current production seams to reuse

- Keep identity / region / venue scoping and cosine threshold.
  Empty/`anonymous` still stores nothing and never hits.
- Compute the embedding from the request `query` as today. Do not
  embed the HMAC.
- Replace `CacheEntry.query_text` with `query_hmac` (hex). Do not
  keep a parallel plaintext field.
- HMAC-SHA256 of UTF-8 query bytes. Constructor-inject the key on
  `SemanticCacheService` so tests can use a known key. The module
  singleton may mint a process-local 32-byte key with
  `secrets.token_bytes` when no key is passed (in-memory cache
  already dies on restart). Do not log the key. Do not add a
  required new env var.
- Do not print or log the raw query when storing.
- R4: do not add a second cache. Do not call supabase cache from
  the orchestrator. Do not change `cached_responses` schema.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.

## Scope

### 1. Store HMAC, not the question

`hmac_query(query: str, key: bytes) -> str` in
`services/cache_service.py` (or a tiny helper next to it).

`store_response` writes `query_hmac=hmac_query(...)`.
`check_cache` does not need the stored HMAC for a hit; cosine
plus identity/region/venue stays the matcher.

If any test constructs `CacheEntry(...)` with `query_text`,
update it. `test_spec43_g8_cache.py` identity tests must stay
green.

### 2. Named tests

Add `tests/test_spec43_g8_hmac.py`.

No widgets. No live Postgres. Use a private
`SemanticCacheService(hmac_key=b"g8-hmac-test-key")` so the
singleton's random key does not matter.

Named tests that must exist with these exact names:

`test_cache_does_not_store_raw_query_text`

Store canary query
`CANARY-g8-hmac-what-is-my-booking-code-XYZ`. Identity
`user-g8-hmac`, region `luang_prabang_laos`, venue
`Wat Xieng Thong`. After store, dump every entry (repr / dict
values / json). The canary substring must not appear. `query_hmac`
is 64 hex chars. `hasattr(entry, "query_text")` is false.

`test_cache_hmac_is_stable_for_the_same_query`

Same private service, same query stored twice (or hmac_query
called twice). The two HMAC hex strings are equal. A different
query produces a different HMAC.

Also add (any name):

- identity isolation still holds (user B does not hit user A's
  stored response)
- unusable identity still stores nothing
- existing `test_semantic_cache_does_not_share_private_response_across_users`
  stays green (do not change that test)

Do not assert on comments.

### 3. R17 sabotage

Exact edit: in `store_response`, set a plaintext `query_text`
attribute on the entry to the raw query (in addition to or
instead of `query_hmac`).

`test_cache_does_not_store_raw_query_text` must fail (canary
appears). Restore before the PR. Do not sabotage by deleting
the test. Do not sabotage identity isolation.

## Out of scope

- Restricted-content canaries
- Trip / date / source-version in the cache key
- Active expiry sweeper (read-time skip stays)
- `supabase_service` cache path / `cached_responses`
- Admin IAM, Armor, Play Integrity
- `derived_feature`, hosted 0026
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
`test_cache_does_not_store_raw_query_text` and
`test_cache_hmac_is_stable_for_the_same_query`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
