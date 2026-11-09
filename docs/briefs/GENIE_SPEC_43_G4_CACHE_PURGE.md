# Genie brief: SPEC-43 Gap 4 slice 9 -- purge in-process caches on erase

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27.

## Goal

Slices 1-8 are on main. After erase, PostgREST rows and the Auth
user are gone and this process refuses the subject for an hour, but
in-process personal caches can still hold that traveller's data
(semantic-cache entries keyed by `identity_scope`, Ask budget
counters, cost-tracker events). Slice 9 drops those for the erased
caller, in this process only, before the denylist step.

Not in this slice: the error ring (entries have no `user_id`), the
Ask exact-match cache (public facts, not identity-scoped), the
`cached_responses` SQL table (Gap 8 / identity `none`), or any
cross-instance store.

## Base

Latest `main` (`4f22d1d`), including Gap 4 slice 8 (PR #184).

Create and push: `feat/spec43-g4-cache-purge`

Do not merge. Do not deploy. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `routers/me_router.py` (erase order: rows, Auth, deny)
- `services/cache_service.py` (`CacheEntry.identity_scope`,
  `normalize_identity_scope`, `clear_expired`, `clear_all`)
- `services/ask_service.py` (`AskBudget.reset`, `_shared_budget`)
- `monitoring/cost_tracker.py` (`CostEvent.user_id`, singleton
  `cost_tracker`)
- `monitoring/error_log.py` (confirm entries have no user id; do not
  change the ring)
- `services/data_rights_token_deny.py` (injection / blank-id style)
- Gap 4 erase-route tests (keep green; extend)

No migration. No Flutter. No change to `security.py`,
`db_provider.py`, `supabase_service.py`, the erase/auth-delete
modules, or the rate-limit exempt list. Do not deploy.

## Scope

### 1. Clear helpers on the existing stores

`services/cache_service.py` -- add:

```
def clear_identity(self, identity_scope: str) -> int:
```

- Normalize with `normalize_identity_scope`. If the result is `None`,
  return 0 and touch nothing (never `clear_all`).
- Remove every `CacheEntry` whose `identity_scope` equals the
  normalized scope. Leave every other entry. Return the count removed.
- Do not log the scope. Do not reset `total_hits` / `total_misses`
  (those are process totals).

`monitoring/cost_tracker.py` -- add:

```
def clear_user(self, user_id: str) -> int:
```

- Blank / non-string -> `ValueError` before mutating.
- Drop every `CostEvent` with that `user_id`. Return the count removed.
- Leave other users' events.

`services/ask_service.py` -- add a one-line public wrapper next to
`_shared_budget`:

```
def reset_ask_budget(user_id: str) -> None:
    _shared_budget.reset(user_id)
```

Do not clear `AskCache` / `_shared_cache` (not identity-scoped).

### 2. `services/data_rights_cache_purge.py`

ASCII only. No supabase import. No print. No logging of user ids.

```
def purge_identity_caches(
    user_id: str,
    *,
    semantic_cache=None,
    costs=None,
    reset_budget=None,
) -> dict:
```

- Blank / non-string `user_id` -> `ValueError` before any call.
- Defaults: `cache_service`, `cost_tracker`, `reset_ask_budget`.
- Call, in order: `semantic_cache.clear_identity(user_id)`,
  `costs.clear_user(user_id)`, `reset_budget(user_id)`.
- Return
  `{"semantic_cache": n, "cost_events": n, "ask_budget": True}`
  (ask_budget is always `True` on success; it has no count).
- Do not catch exceptions from the stores (the route owns the
  generic 500). Do not touch the error ring.

### 3. Wire into `routers/me_router.py`

Order inside the existing `try`, after Auth delete (supabase only)
and **before** `deny_identity`:

```
purge_identity_caches(identity.user_id)
deny_identity(identity.user_id)
```

- Purge for every successful erase, including debug.
- If purge raises, use the same generic 500 path and do **not** deny
  (traveller can retry). Rows/Auth may already be gone; that is the
  same partial-success shape as an Auth-delete failure.
- Response shape unchanged (no cache fields). Update the docstring:
  in-process semantic cache, cost events, and Ask budget for the
  caller are purged; remainders are error-ring-by-identity, Ask
  exact cache, `cached_responses` SQL, cross-instance denylist,
  tombstones, export, retention, Flutter.

### 4. Named tests

New `tests/test_spec43_g4_cache_purge.py`. Extend
`tests/test_spec43_g4_erase_route.py`.

Unit:

- `test_semantic_cache_clear_identity_removes_only_that_scope`
- `test_semantic_cache_clear_identity_blank_or_anonymous_is_noop`
- `test_cost_tracker_clear_user_removes_only_that_user`
- `test_cost_tracker_clear_user_rejects_blank`
- `test_purge_identity_caches_calls_all_three_in_order`
- `test_purge_identity_caches_rejects_blank_before_any_call`
- `test_purge_module_has_no_supabase_import`
- `test_ask_cache_is_not_cleared_by_purge` (seed AskCache; purge; size
  unchanged)

Route:

- `test_erase_route_purges_caller_caches_before_deny`
  Seed semantic-cache entries and cost events for A and B; erase A;
  A's cache/cost gone, B's remain; A is denied afterward.
- `test_erase_route_skips_deny_when_purge_raises`
  Inject a purge that raises `RuntimeError("PURGE-CANARY-g4")` via
  monkeypatch of `routers.me_router.purge_identity_caches`; response
  is generic 500; canary absent from body/logs/capsys; `is_denied(A)`
  is False.
- `test_erase_route_purge_ignores_client_supplied_user_id`
  Query `user_id=B` while erasing as A: only A's caches purged.

Existing Gap 4 / Gap 8 cache / Gap 1 tests stay green.

### 5. R17 sabotage

Exact edit: in the route's `purge_identity_caches` call, when a
`user_id` query parameter is present, purge that value instead of
`identity.user_id`.

`test_erase_route_purge_ignores_client_supplied_user_id` and
`test_erase_route_purges_caller_caches_before_deny` must fail.
Restore before the PR. If Databricks blocks in-place sabotage, an
in-memory pytest plugin that wraps the route is the accepted
substitute. Drop the plugin before the PR.

## Out of scope (record as remainders, do not build)

- Error-ring purge by identity (entries have no user id)
- Clearing the Ask exact-match public cache
- Deleting `cached_responses` SQL rows
- Shared denylist across Cloud Run instances
- Deletion tombstones and the backup-restore proof
- Export document, retention jobs, local SQLCipher wipe, Flutter
- Armor, Play Integrity, deploy, APK, hosted 0026

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter. Do not
"fix" `test_today_tonight_includes_venue_name` (fails near ICT
midnight on main) or `test_sparse_create_with_limited_hours_succeeds`.

## Report

SHA, branch, pytest last line, files touched, purge return dict for
A's erase, and A/B semantic-cache + cost-event counts before/after.
Name the two R17 tests that failed. Named tests in the report must
include `test_erase_route_purges_caller_caches_before_deny` and
`test_erase_route_skips_deny_when_purge_raises`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
