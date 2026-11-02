# Genie brief: SPEC-43 Gap 8 -- refuse restricted cache responses

Landed on `main` as `895045a` (PR #140). Do not re-implement this slice.
Gap 8 trip/date/source-version landed as `606626e` (PR #142).
Remainders: active purge, unused Supabase cache path. Do not
start hosted 0026, Flutter, deploy, or an APK without a new brief.

## Goal

Identity-scoped HMAC entries still keep `response_text`. A LIGHT
answer that echoes a confirmation code, booking note, or auth
token stays in process memory and can be returned on a later hit.

Hits already use cosine on a request-time embedding plus identity,
region, and venue. This slice does not change matching. It
refuses to store a response that contains restricted content.

This is SPEC-43 Gap 8 restricted-content canaries on the live
in-memory cache only. It is not trip/date hashing, not a sweeper,
not wiring `supabase_service.check_cache` / `store_cache`.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 8)
- `docs/ENGINEERING_RULES.md` (R4, R5, R14, R17)
- `services/cache_service.py` (`store_response`, `CacheEntry`)
- `monitoring/redact.py` (token patterns; reuse, do not copy)
- `agents/state_machine.py` (the `cache_service.store_response` call)
- `models/schemas.py` (`TripNode.confirmation_code`, `booking_notes`)
- `tests/test_spec43_g8_cache.py`
- `tests/test_spec43_g8_hmac.py` (must stay green; do not edit)

Base branch: latest `main` (`75925eb`), including Gap 8 HMAC
`5a9f684` (PR #137).

Create and push:

`feat/spec43-g8-canaries`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 8 acceptance includes: restricted-content canaries make the
cache refuse storage. Identity isolation and HMAC of the question
do not stop a booking code sitting in `response_text`.

Do not add trip/date/source-version to the key this slice.
Refuse-on-restricted-response is the first bar.

Do not key the guard off English words such as `booking`. The HMAC
suite stores `Your booking is at the front desk.` That prose must
still store. A canary prefix that exists only in the test file is
not a production guard (R17).

## Current production seams to reuse

- Keep identity / region / venue scoping, HMAC of the query, and
  cosine threshold. Empty/`anonymous` still stores nothing and
  never hits.
- Reuse Gap 10 token detection. Import `redact_secrets` from
  `monitoring/redact.py`. If `redact_secrets(response) != response`,
  the response contains a token/key pattern and must not be stored.
  Do not copy the regexes.
- Extra needles: non-empty `confirmation_code` and `booking_notes`
  from the trip's nodes. Strip; ignore values shorter than 6
  characters (same floor as Gap 10 literals). If any needle is a
  substring of the response, refuse.
- The orchestrator already calls `store_response` after LIGHT
  generation. Collect needles from `state["trip_state"].nodes` and
  pass them in. Do not only test a helper the orchestrator never
  calls (R17).
- Refuse means: append nothing. Do not redact-and-store. Do not
  log the response or the needles.
- R4: do not add a second cache. Do not call supabase cache from
  the orchestrator. Do not change `cached_responses` schema.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.

## Scope

### 1. Refuse restricted responses

`response_is_restricted(response: str, extra_needles=()) -> bool`
in `services/cache_service.py` (or a tiny helper next to it).

True when:

- `redact_secrets(response) != (response or "")`, or
- any extra needle of length >= 6 appears as a substring of the
  response.

`store_response` takes optional `restricted_needles` (default
empty). If `response_is_restricted(response, restricted_needles)`,
return without appending.

`check_cache` is unchanged. A refused store is a miss later.

The state-machine store call passes needles collected from every
node `confirmation_code` and `booking_notes`.

Do not scan the query this slice. HMAC already hides it. Do not
treat venue names or the word `booking` as restricted.

If any existing test stored a response that now matches a Gap 10
token pattern, change that response string only. Do not weaken
the detector.

### 2. Named tests

Add `tests/test_spec43_g8_canaries.py`.

No widgets. No live Postgres. Use a private
`SemanticCacheService(hmac_key=b"g8-canary-test-key")`.

Named tests that must exist with these exact names:

`test_cache_refuses_restricted_response_canary`

Identity `user-g8-canary`, region `luang_prabang_laos`, venue
`Wat Xieng Thong`, query `What time is the boat?`.

Store a response that contains confirmation canary
`CANARY-g8-restricted-BK-XYZ` and pass that string as a
restricted needle (length >= 6). After store: `_cache` is empty
and `check_cache` for the same identity/region/venue/query is
None.

Separately, store a response that contains
`sk-g8canaryRESTRICTED99` with no extra needles. After store:
still empty (Gap 10 `sk-` pattern). Do not put that `sk-` value
in a comment; assert on the cache contents.

`test_cache_stores_ordinary_prose_without_restricted_markers`

Same private service. Store `Temple opens at 08:00 by the river.`
with needle `CANARY-g8-restricted-BK-XYZ` (needle present, not in
the response). After store: one entry, `check_cache` returns that
prose. HMAC of the query is still 64 hex chars. `query_text`
still does not exist.

Also add (any name):

- identity isolation still holds (user B does not hit user A's
  stored ordinary prose)
- unusable identity still stores nothing
- the state-machine `store_response` call passes needles from a
  trip node `confirmation_code` (put the canary on the node and
  in `state["response"]`, then run the same store path production
  uses). After that call, the cache has no new entry.
- existing
  `test_semantic_cache_does_not_share_private_response_across_users`
  and both HMAC named tests stay green (do not change those files)

Do not assert on comments.

### 3. R17 sabotage

Exact edit: in `store_response`, skip the restricted check and
always append when identity is usable.

`test_cache_refuses_restricted_response_canary` must fail (the
confirmation canary and/or the `sk-` response is stored). Restore
before the PR. Do not sabotage by deleting the test. Do not
sabotage identity isolation or HMAC.

## Out of scope

- Trip / date / source-version in the cache key
- Active expiry sweeper (read-time skip stays;
  `clear_expired` already exists)
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
`test_cache_refuses_restricted_response_canary` and
`test_cache_stores_ordinary_prose_without_restricted_markers`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
