# Genie brief: SPEC-43 Gap 4 slice 6 -- authenticated erase route

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27.

## Goal

Slices 1-5 are on main: inventory, plan, executor, in-memory proof,
and `SupabaseEraseBackend` (`54c3c8d`, PR #178). Slice 6 exposes the
executor over HTTP so a traveller can erase their own server rows:

    POST /api/v1/me/erase     body {"confirm": "erase-my-data"}

The route erases only the authenticated caller. There is no user id
in the path or body. This is the first slice that can delete real
data, so the failure modes matter more than the happy path.

The backend is chosen by a FastAPI dependency so tests inject a fake
and production never reaches a delete by accident.

## Base

Latest `main` (`54c3c8d`), including Gap 4 slice 5 (PR #178).

Create and push: `feat/spec43-g4-erase-route`

Do not merge. Do not deploy. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/data_rights_erase.py` (`execute_erase`, `ERASE_STEPS`)
- `services/data_rights_erase_supabase.py` (`SupabaseEraseBackend`)
- `security.py` (`resolve_identity`, `get_current_user_id`)
- `routers/notifications_router.py` (router prefix and the
  dependency-injection-for-tests pattern)
- `routers/debug_router.py` (how a router can answer 404/501 safely)
- `services/db_provider.py` (`IS_SUPABASE`, `db_service`)
- `main.py` (`include_router` block)
- `monitoring/rate_limit.py` (DELETE/POST already counted; do not
  add this path to `_EXEMPT_PATHS`)
- the Gap 4 tests (must stay green)

No new migration. No Flutter. No change to `supabase_service.py`,
`db_provider.py`, `security.py`, or the Gap 4 service modules.
Do not touch hosted configuration. Do not deploy.

## Scope

### 1. Router `routers/me_router.py`

`router = APIRouter(prefix="/api/v1", tags=["me"])`.

`get_erase_backend()` dependency:

- If `services.db_provider.IS_SUPABASE` is true, return
  `SupabaseEraseBackend(db_service.client)`.
- Otherwise raise `HTTPException(501, detail="erase_unavailable")`.
  The in-memory dev `DatabaseService` is not wired this slice; say
  so in the docstring. Never fall back to a different backend.

`POST /me/erase`:

- Auth: `Depends(resolve_identity)`. Only the resolved
  `identity.user_id` is ever erased. Ignore any user id the client
  sends. A request with no or invalid credentials is rejected by
  the existing auth (401) before the backend dependency runs or any
  client call happens.
- Request model: `{"confirm": str}`, `extra="forbid"`. Anything but
  the exact string `erase-my-data` returns 422 and calls the backend
  zero times.
- On success: `execute_erase(identity.user_id, backend)`; respond
  200 with
  `{"status": "erased", "tables": [{"table": ..., "rows": n}, ...]}`.
  Do not echo the user id, trip ids, `via`, or any row content.
- On any backend exception: respond 500 with the fixed body
  `{"detail": "erase_incomplete"}`. Do not include exception text,
  the failing table, the user id, or the exception class in the
  response. Log one WARNING on logger `travelbuddy` with the
  exception class name and the request id only (no user id, no
  table, no message). Do not retry inside the route.
- The route is safe to call again: a repeat run on a partly erased
  account completes the remaining steps. State this in the
  docstring; test it.
- Do not create the user record as a side effect (do not call
  `get_or_create_user`).

Register the router in `main.py` next to the others. Do not add
the path to the rate-limit exempt list.

### 2. Named tests

New file `tests/test_spec43_g4_erase_route.py`. No network, no live
Supabase. Use the app's `TestClient` and
`app.dependency_overrides[get_erase_backend]` with
`SupabaseEraseBackend(fake_client)`. Reuse the fake client shape from
`tests/test_spec43_g4_erase_supabase.py` by copying it (do not
import across test files). Authenticate the way the existing router
tests do (override `resolve_identity` / `get_current_user_id`, or a
real signed test JWT if that is the repo pattern). Pop overrides in
a `finally`.

Exact names:

- `test_erase_route_erases_only_the_authenticated_user`
  A and B seeded. Authenticated as A: A has zero rows, B's per-table
  counts unchanged. Response is 200 with `status == "erased"`.
- `test_erase_route_requires_authentication`
  No credentials -> 401, zero client ops.
- `test_erase_route_requires_exact_confirmation`
  Missing body, wrong string, extra fields, empty string -> 422;
  zero client ops.
- `test_erase_route_ignores_client_supplied_user_id`
  Body or query carrying B's id still erases only A (extra fields in
  the body are 422; a `?user_id=B` query is ignored).
- `test_erase_route_failure_is_generic_and_leaks_nothing`
  Backend raises `RuntimeError("ERASE-CANARY-g4-route trip_party")`
  on the second step. Response is 500 with exactly
  `{"detail": "erase_incomplete"}`; the canary, the table name, and
  the user id are absent from the response body and from `caplog`
  text and `capsys` output.
- `test_erase_route_is_retryable_after_a_partial_failure`
  First call fails midway; second call (healthy backend) finishes and
  leaves A with zero rows while B is unchanged.
- `test_erase_route_returns_501_when_no_supabase_backend`
  With no override and `IS_SUPABASE` false (monkeypatch), the route
  returns 501 `erase_unavailable` and no client is built.
- `test_erase_route_does_not_create_a_user_record`
- `test_erase_route_counts_toward_the_rate_limit`
  The path is not in the rate-limit exempt set (assert against
  `monitoring.rate_limit`'s exempt paths).
- `test_response_contains_no_identifiers`
  The 200 body has only `status` and `tables` (`table`, `rows`).

The Gap 4 service tests and the Gap 11 rate tests stay green.

### 3. R17 sabotage

Exact edit: in the route, replace `identity.user_id` with a value read
from the `user_id` query parameter when present.

`test_erase_route_ignores_client_supplied_user_id` and
`test_erase_route_erases_only_the_authenticated_user` must fail
(B is erased). Restore before the PR. If Databricks blocks in-place
sabotage, an in-memory pytest plugin that wraps the route is the
accepted substitute. Drop the plugin before the PR.

## Out of scope (record as remainders, do not build)

- Deleting the Supabase Auth (GoTrue) identity. After this route the
  JWT still verifies until it expires, and the next authenticated call
  re-creates a `user_tiers` row. Say this in the docstring.
- Deletion tombstones and the backup-restore proof
- Purging the in-process semantic cache and error ring for the identity
- Export document, retention jobs, local SQLCipher wipe
- The Flutter client flow and sign-out wipe
- Wiring the in-memory dev `DatabaseService`
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

SHA, branch, pytest last line, files touched, the final route path,
the recorded client op list for A's erase through the route, and A/B
row totals before and after. Name the two R17 tests that failed.
Named tests in the report must include
`test_erase_route_erases_only_the_authenticated_user` and
`test_erase_route_failure_is_generic_and_leaks_nothing`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
