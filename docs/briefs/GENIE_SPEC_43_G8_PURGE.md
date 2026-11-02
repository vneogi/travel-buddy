# Genie brief: SPEC-43 Gap 8 -- purge expired in-memory cache entries

This is the open Gap 8 active-purge slice. Implement it. Do not
start admin IAM, Armor, Play Integrity, a `derived_feature` table,
hosted 0026, Flutter, deploy, or an APK. Do not wire
`supabase_service.check_cache` / `store_cache` /
`clear_expired_cache`.

## Goal

`CacheEntry.is_expired` and `SemanticCacheService.clear_expired`
already exist. `check_cache` skips expired rows with `continue`
and leaves them in `_cache`. Nothing in production calls
`clear_expired`. An expired LIGHT answer, including one that once
held traveller prose, stays in process memory until restart.

Gap 8 acceptance: expired rows are deleted from memory. The SQL
`cached_responses` path is unused; do not wire it this slice.

This is SPEC-43 Gap 8 active purge on the live in-memory cache
only.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 8)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `services/cache_service.py` (`is_expired`, `clear_expired`,
  `check_cache`, `store_response`)
- `config/settings.py` (`cache_ttl_hours` -- do not change)
- `tests/test_spec43_g8_cache.py`
- `tests/test_spec43_g8_hmac.py`
- `tests/test_spec43_g8_canaries.py`
- `tests/test_spec43_g8_context.py`

Those four test files must stay green. Do not edit them.

Base branch: latest `main` (`33d3995`), including Gap 8
trip/date/source-version `606626e` (PR #142).

Create and push:

`feat/spec43-g8-purge`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Read-time skip is not deletion. A dump of `_cache`, a debug ring,
or a later hit after TTL if skip is buggy, still has the entry.

Do not add a background thread, `asyncio.create_task`, or a
lifespan loop. Cloud Run instances already die; the hole is
expired rows sitting in `_cache` between requests. Call the
existing `clear_expired` on the live check and store paths.

## Current production seams to reuse

- Keep identity / region / venue / trip / local_date /
  source_version, HMAC of the query, cosine threshold, and
  restricted-response refusal. Empty/`anonymous` still stores
  nothing and never hits.
- Reuse `clear_expired`. Do not rewrite the filter. Do not change
  `cache_ttl_hours`.
- Call `self.clear_expired()` at the start of both `check_cache`
  and `store_response`, before the identity early-return, so an
  anonymous request still drops other identities' expired rows.
- After that call, `check_cache` may keep the `if entry.is_expired:
  continue` guard (harmless). Do not treat skip-only as the fix.
- Do not log the dropped response or query HMAC.
- R4: do not add a second cache. Do not call supabase
  `clear_expired_cache`. Do not change `cached_responses` schema.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.

## Scope

### 1. Delete expired rows on the live path

`check_cache` and `store_response` each call `clear_expired()`
first. After a check or a store, `_cache` contains only
non-expired entries.

### 2. Named tests

Add `tests/test_spec43_g8_purge.py`.

No widgets. No live Postgres. Use a private
`SemanticCacheService(hmac_key=b"g8-purge-test-key")`.

Named tests that must exist with these exact names:

`test_cache_deletes_expired_entries_on_check`

Identity `user-g8-purge`, region `luang_prabang_laos`, venue
`Wat Xieng Thong`, query `What time is the boat?`, ordinary prose
`The boat leaves at 09:30 from the pier.` Store once (defaults
for trip/date/version are fine). Set that entry's `expires_at` to
a UTC datetime in the past. Call `check_cache` with the same
identity/region/venue/query. Result is None. `svc._cache` is
empty. The prose must not appear in `repr` / `vars` of remaining
entries (there should be none).

`test_cache_deletes_expired_entries_on_store`

Store two entries for the same identity (different queries so
both exist). Expire only the first (`expires_at` in the past).
`store_response` a third ordinary query. After store: the expired
entry is gone, the still-fresh second entry remains, the new
third entry is present. `check_cache` for the expired query is
None.

Also add (any name):

- identity isolation still holds on unexpired entries
- unusable identity still stores nothing, and still purges
  expired rows belonging to someone else
- restricted-response refusal still holds
- existing identity, HMAC, canary, and context named tests stay
  green (do not change those files)

Do not assert on comments. Do not freeze wall-clock "today"
against ICT midnight; set `expires_at` explicitly.

### 3. R17 sabotage

Exact edit: in `check_cache`, do not call `clear_expired` (leave
the skip-`continue` only).

`test_cache_deletes_expired_entries_on_check` must fail (expired
entry still in `_cache` after the check). Restore before the PR.
Do not sabotage by deleting the test. Do not sabotage identity
isolation, HMAC, restricted refusal, or trip/date matching.

## Out of scope

- `supabase_service` cache path / `cached_responses` /
  `clear_expired_cache`
- Changing `cache_ttl_hours`
- Background threads / lifespan loops
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

Do not "fix" `test_today_tonight_includes_venue_name`.

## Report

SHA, branch, pytest last line, files touched. Named tests in the
report must include
`test_cache_deletes_expired_entries_on_check` and
`test_cache_deletes_expired_entries_on_store`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
