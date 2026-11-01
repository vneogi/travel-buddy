# Genie brief: SPEC-43 Gap 8 -- identity-scope the semantic cache

This is the open Gap 8 first slice. Implement it. Do not start
Gap 10, Gap 11, remaining Gap 9 GPS/`derived_feature`, hosted 0026,
Flutter, deploy, or an APK.

## Goal

Two travellers asking a similar question must not share a cached
private response.

Today `SemanticCacheService` keys entries by `geo_region` and
`venue_name` only. `check_cache` / `store_response` take no
identity. `Orchestrator._node_check_cache` and the LIGHT store
path pass region and venue from the trip, not `state["user_id"]`.
ASK_INFO already bypasses this cache.

This is SPEC-43 Gap 8 identity isolation on the live in-memory
cache only. It is not HMAC-of-query, not restricted-content
canaries, not trip/date/source-version hashing, not active purge
beyond the existing expiry skip, not wiring `supabase_service`
`check_cache` / `store_cache` into the live path, not a
`cached_responses` migration.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 8)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `services/cache_service.py`
- `agents/state_machine.py` (`_node_check_cache`, LIGHT
  `store_response`)
- `tests/test_spec37_production_blockers.py` (geo/venue cache tests)
- `services/supabase_service.py` (`check_cache` / `store_cache` --
  unused on the live path; do not wire)

Base branch: latest `main` (`e3eaa81`), including Gap 7
`e3eaa81` (PR #112).

Create and push:

`feat/spec43-g8-cache`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Region plus venue is not an owner. The same LIGHT question from
user A and user B in Luang Prabang at the same stop would share
prose. Gap 12 already identity-scopes on-device trip/place files.
This slice does the same for the process-wide semantic cache.

Do not build the full Gap 8 ledger this slice. Identity on every
live cache entry is the first bar.

## Current production seams to reuse

- Keep `(geo_region, venue_name)` scoping. Add `identity_scope`.
  A hit requires all three plus cosine >= threshold.
- `state["user_id"]` is already on the orchestrator state. Pass it
  through. Do not invent a second identity string.
- Empty, whitespace, or the literal `anonymous` is not a scope:
  `check_cache` returns None and `store_response` does not append.
  The default `user_id="anonymous"` on `process_event` must not
  become a shared bucket.
- Expired entries are already skipped on read. Do not add a new
  sweeper this slice.
- R4: do not add a second in-memory cache. Do not call
  `supabase_service.check_cache` from the orchestrator.

No CREATE TABLE. If you somehow add one, grant `service_role`
only. Do not apply 0026. No Flutter. No live Postgres.

## Scope

### 1. Cache entry identity

In `services/cache_service.py`:

- `CacheEntry` stores `identity_scope: str`.
- `check_cache` and `store_response` take `identity_scope: str`
  (required; no default that would keep old callers compiling
  without a scope).
- Compare scopes with exact string equality after strip. Do not
  treat missing identity as global.
- `clear_all` / `clear_expired` / stats stay as they are.

Update `tests/test_spec37_production_blockers.py` cache tests to
pass a non-empty identity. Same-region hit still works for that
one user. Cross-region / cross-venue misses still work.

### 2. Orchestrator

`_node_check_cache` and the LIGHT `store_response` call must pass
`identity_scope=state["user_id"]`.

Do not start caching ASK_INFO. Do not cache structural edits.

### 3. Named tests

Add `tests/test_spec43_g8_cache.py`.

In-memory `cache_service` only. No widgets. No live Postgres.

Named test that must exist with this exact name:

`test_semantic_cache_does_not_share_private_response_across_users`

Store under user A, same query / region / venue, check as user B:
hit is None. Check as user A: hit is the stored prose.

Also add (any name):

- empty / `anonymous` identity: store is a no-op, check is None
- existing geo isolation still holds when identity matches
  (can live in the SPEC-37 tests once they pass identity)

Do not assert on comments.

### 4. R17 sabotage

Exact edit: in `check_cache`, stop requiring `identity_scope`
equality (keep region/venue).

`test_semantic_cache_does_not_share_private_response_across_users`
must fail. Restore before the PR. Do not sabotage by deleting the
test. Do not sabotage geo/venue isolation.

## Out of scope

- HMAC or dropping raw `query_text`
- Restricted-field canaries
- Trip id / date / source-version in the key
- Active delete of expired rows on a timer
- `cached_responses` SQL, `check_semantic_cache` RPC
- Gap 7 Flutter outbox, Gap 9 GPS, Gap 10, Gap 11
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
the report must be
`test_semantic_cache_does_not_share_private_response_across_users`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
