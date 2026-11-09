# Genie brief: SPEC-43 Gap 4 slice 7 -- delete the Auth identity

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27.

## Goal

Slices 1-6 are on main. Slice 6 exposed `POST /api/v1/me/erase`,
but it only deletes PostgREST rows. The GoTrue Auth user stays, so a
still-valid access token keeps verifying until `exp`, and the next
authenticated call recreates a `user_tiers` row. Slice 7 deletes the
Auth identity for the authenticated caller, after the row erase
succeeds.

Order is load-bearing: rows first, Auth second. If Auth is deleted
first and the row erase fails, the traveller cannot authenticate to
retry. A missing Auth user on retry is success (idempotent).

The admin client is injected. No live Supabase. No network. No new
settings, no migration, no Flutter.

## Base

Latest `main` (`2764280`), including Gap 4 slice 6 (PR #180).

Create and push: `feat/spec43-g4-auth-delete`

Do not merge. Do not deploy. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `routers/me_router.py` (current erase route, response/error shape,
  `get_erase_backend`, docstring remainders)
- `security.py` (`ResolvedIdentity.user_id`, `identity_kind` values
  `supabase` and `debug`)
- `services/data_rights_erase.py` / `data_rights_erase_supabase.py`
  (injection style; do not change them)
- `services/supabase_service.py` (how `client` is obtained; do not
  change it)
- `services/db_provider.py` (`IS_SUPABASE`, `db_service`)
- `tests/test_spec43_g4_erase_route.py` (override / debug-header
  patterns; keep green and extend)

No change to `security.py`, `db_provider.py`, `supabase_service.py`,
the Gap 4 erase modules, migrations, rate-limit exempt list, or
hosted configuration. Do not deploy.

## Scope

### 1. `services/data_rights_auth_delete.py`

ASCII only. No `supabase` import. No logging of user ids. No print.

```
class AuthIdentityDeleter(Protocol):
    def delete_auth_user(self, user_id: str) -> None: ...
```

- `NoOpAuthIdentityDeleter`: `delete_auth_user` is a no-op after the
  blank-id check.
- `SupabaseAuthIdentityDeleter(client)`:
  - Blank / non-string `user_id` -> `ValueError` before any client call.
  - Otherwise call `client.auth.admin.delete_user(str(user_id))`.
  - Never call any other admin method. Never list users. Never pass a
    filterless or bulk delete.
  - If the admin call raises and `_is_missing_user(exc)` is true
    (HTTP/status 404, or a message containing `not found` /
    `User not found`, case-insensitive), treat as success and return.
    Any other exception re-raises unchanged.
  - `_is_missing_user` must not import supabase exception types; inspect
    the exception object only (`status_code` / `code` / `message` /
    `str(exc)`).

### 2. Wire into `routers/me_router.py`

`get_auth_deleter()` dependency:

- If `IS_SUPABASE`, return `SupabaseAuthIdentityDeleter(db_service.client)`.
- Otherwise return `NoOpAuthIdentityDeleter()`.
  (Same importlib pattern as `get_erase_backend`. Tests override this
  dependency; do not construct a real admin client in tests.)

In `erase_me`, after `execute_erase` returns successfully:

- If `identity.identity_kind == "supabase"`, call
  `auth_deleter.delete_auth_user(identity.user_id)`.
- If `identity.identity_kind == "debug"`, do not call the deleter
  (debug identities have no GoTrue user; a debug header must never
  delete an Auth row).
- Any exception from the Auth delete uses the same path as a row-erase
  failure: 500 `{"detail": "erase_incomplete"}`, one WARNING on
  `travelbuddy` with exception class name and request id only (no
  user id). Do not roll back the row erase (there is no transaction
  across PostgREST and GoTrue). Retry is the recovery: a second call
  finds zero rows, then retries Auth delete.
- Response shape on success is unchanged (`status` + `tables` only).
  Do not add an Auth field.
- Update the module docstring: Auth identity deletion is now in scope
  for `identity_kind == "supabase"`; remainders are still tombstones,
  cache/ring purge, export, retention, Flutter, and the fact that a
  still-unexpired access token may verify at the API until `exp`
  (no denylist this slice; Gap 6 already records that).

Do not call Auth delete before the row erase. Do not call
`get_or_create_user`. Do not add the path to the rate-limit exempt
list.

### 3. Named tests

New file `tests/test_spec43_g4_auth_delete.py` for the deleter unit
tests (fake `client.auth.admin`, no network). Extend
`tests/test_spec43_g4_erase_route.py` for the route wiring (override
`get_auth_deleter`; keep the existing erase override).

Exact names:

Unit (`test_spec43_g4_auth_delete.py`):

- `test_supabase_auth_delete_calls_admin_with_string_id`
- `test_supabase_auth_delete_rejects_blank_user_id_before_any_call`
- `test_supabase_auth_delete_missing_user_is_success`
- `test_supabase_auth_delete_other_errors_propagate`
- `test_noop_auth_delete_never_touches_a_client`
- `test_auth_deleter_has_no_supabase_import`

Route (add to `test_spec43_g4_erase_route.py`):

- `test_erase_route_deletes_auth_after_rows_for_supabase_identity`
  Override `resolve_identity` to return
  `ResolvedIdentity(USER_A, "supabase")`. Fake deleter records calls.
  Assert: row erase happens, then exactly one
  `delete_auth_user(USER_A)`, and B is never passed.
- `test_erase_route_skips_auth_delete_for_debug_identity`
  Default debug-header path: deleter call list stays empty after a
  200 erase.
- `test_erase_route_does_not_delete_auth_when_row_erase_fails`
  Backend raises on step 2; deleter call list stays empty; response
  is the generic 500.
- `test_erase_route_auth_delete_failure_is_generic_and_leaks_nothing`
  Rows succeed; deleter raises
  `RuntimeError("AUTH-CANARY-g4-delete " + USER_A)`. Response is
  exactly `{"detail": "erase_incomplete"}`; canary and user id absent
  from response, `caplog`, and `capsys`. Rows for A are already gone
  (no rollback).
- `test_erase_route_auth_delete_retry_after_partial_success`
  First call: rows erase, Auth raises. Second call: rows already 0,
  Auth succeeds. Final A row counts are zero; deleter saw two calls
  for A only.
- `test_erase_route_auth_delete_ignores_client_supplied_user_id`
  Query `user_id=B` while authenticated as A (supabase identity):
  deleter receives only A.

Existing Gap 4 route and service tests stay green.

### 4. R17 sabotage

Exact edit: in the route's Auth-delete call, when a `user_id` query
parameter is present, pass that value instead of `identity.user_id`.

`test_erase_route_auth_delete_ignores_client_supplied_user_id` and
`test_erase_route_deletes_auth_after_rows_for_supabase_identity`
must fail (B is deleted, or B is passed to the deleter). Restore
before the PR. If Databricks blocks in-place sabotage, an in-memory
pytest plugin that wraps the route is the accepted substitute. Drop
the plugin before the PR.

## Out of scope (record as remainders, do not build)

- Access-token denylist / immediate JWT invalidation before `exp`
- Deletion tombstones and the backup-restore proof
- Purging the in-process semantic cache and error ring
- Export document, retention jobs, local SQLCipher wipe
- The Flutter client flow and sign-out wipe
- Wiring the in-memory dev `DatabaseService` to the erase route
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

SHA, branch, pytest last line, files touched, the Auth-delete call
order relative to the row-erase ops, and A/B deleter-argument lists
for the supabase-identity route test. Name the two R17 tests that
failed. Named tests in the report must include
`test_erase_route_deletes_auth_after_rows_for_supabase_identity` and
`test_erase_route_auth_delete_failure_is_generic_and_leaks_nothing`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
