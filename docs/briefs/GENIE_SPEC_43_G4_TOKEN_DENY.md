# Genie brief: SPEC-43 Gap 4 slice 8 -- erase token denylist

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27.

## Goal

Slices 1-7 are on main. Slice 7 deletes the GoTrue Auth user after
the row erase, but `resolve_identity` only verifies the JWT. A
still-unexpired access token keeps working until `exp`, and the next
authenticated call can recreate a `user_tiers` row. Slice 8 closes
that window inside this process: after a successful erase, the
caller's `user_id` is denied until a fixed TTL, and every identity
path refuses a denied id with 401.

Process-local only (same class as the error ring). Shared storage
across Cloud Run instances is a recorded remainder, not this slice.

## Base

Latest `main` (`ea5c0b3`), including Gap 4 slice 7 (PR #182).

Create and push: `feat/spec43-g4-token-deny`

Do not merge. Do not deploy. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `security.py` (`resolve_identity`, JWKS / HS256 / debug paths,
  `_unauthorized`)
- `routers/me_router.py` (erase order: rows, then Auth for supabase,
  response/error shape)
- `services/data_rights_auth_delete.py` (injection style)
- `monitoring/error_log.py` (process-local + lock pattern to mirror)
- `tests/test_spec43_g1_anon_jwt.py` (`make_token` / `jwks` fixture)
- `tests/test_spec43_g4_erase_route.py` (override patterns; keep green)

No migration. No Flutter. No Redis. No change to
`db_provider.py`, `supabase_service.py`, the Gap 4 erase/auth-delete
modules (other than what the route needs), or the rate-limit exempt
list. Do not deploy. Do not touch hosted configuration.

## Scope

### 1. `services/data_rights_token_deny.py`

ASCII only. No network. No supabase import. No print. Do not log
user ids.

```
DENY_TTL_SECONDS = 3600  # covers the default Supabase access-token lifetime
```

- `deny_identity(user_id: str, *, now: datetime | None = None) -> datetime`
  Blank / non-string `user_id` -> `ValueError` before any store write.
  Stores `user_id -> until` where `until = (now or utcnow) + DENY_TTL_SECONDS`.
  Re-denying the same id extends (or refreshes) `until`. Returns `until`.
- `is_denied(user_id: str, *, now: datetime | None = None) -> bool`
  Blank / non-string -> `False` (never raises on the read path used by
  auth). Drops expired entries on read. True only while `now < until`.
- `reset_denylist()` for tests.
- Thread-safe (`threading.Lock`), same spirit as `ErrorLog`.
- Module-level singleton store. No settings knobs this slice.

### 2. `security.py`

In `resolve_identity`, after a `user_id` is successfully resolved from
JWKS, HS256, or the debug header, and before returning
`ResolvedIdentity`:

- If `is_denied(user_id)`: raise `_unauthorized("Access token has been revoked")`
  (same 401 shape as other auth failures; do not include the user id).
- Import `is_denied` from the new module. Do not otherwise change claim
  checks, JWKS behaviour, or debug gating.

### 3. `routers/me_router.py`

After the row erase succeeds and (for supabase) the Auth delete
returns, call `deny_identity(identity.user_id)`.

- Deny for every successful erase, including `identity_kind == "debug"`
  (so a debug header cannot keep using the same id after erase).
- Order: rows -> Auth delete (supabase only) -> deny. If Auth delete
  raises, do not deny (same generic 500; traveller can retry).
- Deny itself must not raise in normal use; if it somehow does, use the
  same generic 500 path.
- Response shape unchanged. Update the docstring: denylist is now in
  scope for this process for `DENY_TTL_SECONDS`; remainders are
  cross-instance sharing, tombstones, cache/ring purge, export,
  retention, Flutter.

### 4. Named tests

New file `tests/test_spec43_g4_token_deny.py`. Extend the erase-route
tests for wiring. Keep Gap 1 JWKS tests green.

Exact names (unit):

- `test_deny_identity_rejects_blank_before_store`
- `test_is_denied_true_until_ttl_then_false`
- `test_re_deny_extends_until`
- `test_is_denied_blank_is_false`
- `test_reset_denylist_clears_all`
- `test_deny_module_has_no_supabase_import`

Exact names (security / route):

- `test_resolve_identity_jwks_refuses_denied_user`
  JWKS fixture + `make_token(sub=A)`; after `deny_identity(A)`,
  bearer of that token gets 401 with the revoked detail; B still works.
- `test_resolve_identity_debug_refuses_denied_user`
  Debug header path: denied id -> 401; other id still works.
- `test_erase_route_denies_caller_after_success`
  Successful erase (debug identity) -> `is_denied(USER_A)`; B not denied.
  A subsequent request as A is 401 before any erase backend call.
- `test_erase_route_does_not_deny_when_row_erase_fails`
- `test_erase_route_does_not_deny_when_auth_delete_fails`
  Supabase identity; Auth deleter raises; A is not denied; generic 500.
- `test_erase_route_deny_ignores_client_supplied_user_id`
  Query `user_id=B` while erasing as A: only A is denied.

### 5. R17 sabotage

Exact edit: in the route's `deny_identity` call, when a `user_id`
query parameter is present, deny that value instead of
`identity.user_id`.

`test_erase_route_deny_ignores_client_supplied_user_id` and
`test_erase_route_denies_caller_after_success` must fail (B denied,
or A not denied). Restore before the PR. If Databricks blocks
in-place sabotage, an in-memory pytest plugin that wraps the route
is the accepted substitute. Drop the plugin before the PR.

## Out of scope (record as remainders, do not build)

- Shared denylist across Cloud Run instances (Redis / DB)
- Per-`jti` revocation (this slice denies the subject)
- Deletion tombstones and the backup-restore proof
- Purging the in-process semantic cache and error ring
- Export document, retention jobs, local SQLCipher wipe
- The Flutter client flow
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

SHA, branch, pytest last line, files touched, deny TTL used, and
A/B `is_denied` before/after the successful erase test. Name the two
R17 tests that failed. Named tests in the report must include
`test_erase_route_denies_caller_after_success` and
`test_resolve_identity_jwks_refuses_denied_user`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
