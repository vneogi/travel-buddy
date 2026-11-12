# Genie brief: SPEC-43 Gap 4 slice 14 -- HTTP export route

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

Gap 4 is data rights (export, deletion, retention). On main already:
the data-rights inventory, the erase plan and executor, in-memory and
Supabase erase backends, `POST /api/v1/me/erase` (with Auth delete,
process-local denylist, and in-process cache purge), the export plan,
the export executor, the in-memory export backend, and
`SupabaseExportBackend` (`f7802ad`, PR #196). This slice adds the HTTP
route that runs `execute_export` for the authenticated caller through
an injected export backend. Nesting, human-readable documents, file
download, and pagination stay remainders.

## 1. Goal and the one property that matters

`GET /api/v1/me/export` returns the authenticated caller's identity
rows and nobody else's. The user id comes only from
`resolve_identity`. No user id is read from the path, query, or body.
A hostile `?user_id=` or body field must not change whose rows are
fetched. The response is the flat per-table result of `execute_export`
(table name plus row list); it is not nested under trips and not a
downloadable document.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `routers/me_router.py`, `services/data_rights_export.py`,
   `services/data_rights_export_supabase.py`,
   `services/data_rights_export_memory.py`,
   `tests/test_spec43_g4_erase_route.py`,
   `tests/test_spec43_g4_export_supabase.py`,
   `docs/ENGINEERING_RULES.md`.
3. Confirm `tests/test_spec43_g4_export_route.py` does NOT exist yet,
   and `origin/feat/spec43-g4-export-route` does not exist. If either
   exists, this slice may already be done: stop and report.
4. Do not start from a branch you made earlier. Create a fresh branch
   from that main: `feat/spec43-g4-export-route`.

Never start work from an older SHA. An earlier Gap 3 branch was built on
a stale base and, if merged, would have deleted most of Gap 4. Check the
base before you write a line.

## 3. Read before editing (read only; these are your patterns)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16 (no hard-coded pytest
  counts in docs), R17 (a guard that cannot fail is not a guard).
- `routers/me_router.py`: the erase route. Mirror its dependency
  injection, 501 path, generic 500 path, and logging shape. Do not
  copy Auth delete, denylist, or cache purge into the export path;
  those belong to erase only.
- `services/data_rights_export.py`: `execute_export`, `EXPORT_STEPS`,
  `ExportBackend`.
- `services/data_rights_export_supabase.py`: the backend the route
  wires when Supabase is configured.
- `tests/test_spec43_g4_erase_route.py`: FastAPI TestClient,
  dependency override, debug-header auth, canary failure pattern.
- `tests/test_spec43_g4_export_supabase.py`: fake client and seeding
  shape to copy for export (read-only fake; no write methods).

## 4. Files you may touch

- `routers/me_router.py` (add the export route, dependency, and
  response models; leave the erase path behaviour unchanged)
- `tests/test_spec43_g4_export_route.py` (new)

Nothing else. In particular do NOT change:

- `services/data_rights_export.py`,
  `services/data_rights_export_memory.py`,
  `services/data_rights_export_supabase.py`
- any `services/data_rights_erase*.py`,
  `services/data_rights_auth_delete.py`,
  `services/data_rights_token_deny.py`,
  `services/data_rights_cache_purge.py`
- `security.py`, `main.py`, `config/data_rights.py`,
  `services/db_provider.py`, `services/supabase_service.py`
- `monitoring/` (including `monitoring/rate_limit.py`) and
  `tests/conftest.py`
- any existing test file (do not edit, delete, or loosen a single line
  of an existing test; if one breaks, stop and report)
- any doc, any brief, `PROJECT_STATUS`, `HANDOFF`, `DOCUMENT_MAP`

Do not write a new brief or any doc. Do not start slice 15.

## 5. The route: add to `routers/me_router.py`

ASCII only. Keep the module's existing erase behaviour byte-identical
in spirit: no drive-by refactors of erase helpers, no renaming, no
reordering of erase steps.

### 5.1 Dependency `get_export_backend`

Mirror `get_erase_backend`:

- Use `importlib.import_module("services.db_provider")` (the services
  package attribute can shadow the submodule).
- If not `provider.IS_SUPABASE`: raise
  `HTTPException(501, detail="export_unavailable")`.
- Otherwise return `SupabaseExportBackend(provider.db_service.client)`.
- Never fall back to `InMemoryExportBackend` or any other store.
- Do not call `get_or_create_user`.

### 5.2 Models

- No request body. This is a GET.
- Response model:
  - `status: Literal["exported"]`
  - `tables: List[{table: str, rows: List[dict]}]`
  - Use Pydantic models with `extra="forbid"` on any request/response
    wrapper you add. Prefer a small `ExportedTable` with
    `table: str` and `rows: List[dict]`, and an `ExportResponse` with
    `status` and `tables`.
- The route must not invent nesting under trips. Pass through the flat
  list `execute_export` already returns (each result's `table` and
  `rows`). Drop `method` and `via` from the HTTP response; those are
  internal plan fields.

### 5.3 Handler `GET /api/v1/me/export`

Dependencies, in this order: `Request`, `resolve_identity`,
`get_export_backend`.

Behaviour:

1. Call `execute_export(identity.user_id, backend)`.
2. On success, return
   `{"status": "exported", "tables": [{"table": ..., "rows": ...}, ...]}`
   in `EXPORT_STEPS` order.
3. On any exception: log one WARNING on logger `travelbuddy` with the
   exception class name and `request_id` only
   (`"export incomplete (%s) request_id=%s"`), return
   `JSONResponse(500, {"detail": "export_incomplete"})`. No exception
   text, table name, user id, row content, or canary in the body or
   logs beyond the class name.
4. Do not deny the caller, do not purge caches, do not delete Auth.
5. Do not create a user record.

Constants (module level, next to the erase ones):

- `EXPORT_UNAVAILABLE = "export_unavailable"`
- `EXPORT_INCOMPLETE = "export_incomplete"`

Update the module docstring briefly to mention the export route and
that nesting / document download / pagination remain out of scope, and
that the Gap 11 limiter does not count GET, so export is not throttled
yet (remainder). Leave the erase documentation intact.

## 6. The tests: `tests/test_spec43_g4_export_route.py`

No network. No `supabase` package.

Copy the read-only fake client from
`tests/test_spec43_g4_export_supabase.py` into this file (do not import
across test files). Seed users A and B the same way. Auth uses the
suite's debug header path (`X-Debug-User-Id`) through the real
`resolve_identity`, exactly as the erase-route tests do.

Override `get_export_backend` with
`SupabaseExportBackend(fake)`. Use
`TestClient(app, raise_server_exceptions=False)`.

Exact test names (each must exist; add more only if they add proof):

1. `test_export_route_returns_only_the_authenticated_users_rows`
   `GET /api/v1/me/export` as A. Status 200, `status == "exported"`.
   Tables follow `EXPORT_STEPS` order. Every returned row belongs to A
   (use the test-only `seed_owner` marker). Per-table counts equal A's
   seeded counts (derive them; no hard-coded numbers). B's store rows
   are unchanged. Response must not contain B's user id string.
2. `test_export_route_requires_authentication`
   No auth header -> 401. Fake store unchanged. No reads recorded
   (or, if the app hits the backend only after auth, `client.ops`
   stays empty either way; assert empty ops).
3. `test_export_route_ignores_client_supplied_user_id`
   Authenticated as A, send `?user_id=B` (and, if you also try a body
   on GET, ignore it). Returned rows are still only A's. B's rows are
   untouched. This is the R17-reachable hostility test: the sabotage
   in section 7 must make this fail.
4. `test_export_route_failure_is_generic_and_leaks_nothing`
   Make the fake raise `RuntimeError("EXPORT-CANARY-g4-route")` on a
   mid-plan table (for example `trip_node`). Expect 500
   `{"detail": "export_incomplete"}`. The canary string, user ids, and
   table names must not appear in the response body. Caplog: exactly
   one WARNING on `travelbuddy` containing the exception class name
   and a request id; the canary string must not appear in the log
   message. Capsys stdout/stderr empty of the canary.
5. `test_export_route_returns_501_when_no_supabase_backend`
   Monkeypatch `IS_SUPABASE` to False, clear the
   `get_export_backend` override so the real dependency runs, expect
   501 `{"detail": "export_unavailable"}`.
6. `test_export_route_does_not_create_a_user_record`
   Monkeypatch whatever `get_or_create_user` path the erase tests use
   (same approach) and assert it is not called.
7. `test_export_route_does_not_deny_or_purge`
   After a successful export of A, `is_denied(A)` is False (reset the
   denylist in an autouse fixture as the erase tests do). The export
   path must not call `deny_identity` or `purge_identity_caches`.
8. `test_export_route_response_omits_method_and_via`
   Each table entry in the JSON has exactly the keys `table` and
   `rows` (no `method`, no `via`).
9. `test_export_route_is_not_exempt_from_the_rate_limiter`
   Assert the export path (trailing slash stripped, as the erase test
   does) is not in `rate_limit._EXEMPT_PATHS`, and that
   `(EXPORT_PATH, "GET")` is a registered app route. Do NOT assert
   that GET is counted, and do NOT assert that GET is uncounted.
   `monitoring/rate_limit.py` counts only POST/PUT/PATCH/DELETE by
   Gap 11 design (see its module docstring: "GETs and payment webhooks
   are not counted"), so a GET export is currently not throttled. That
   is a recorded remainder (section 10), not part of this slice.
   Pinning "uncounted" would break the future limiter slice, and
   asserting "counted" is false today. Do not edit `monitoring/` or
   `tests/conftest.py` to make a stronger assertion pass.
10. `test_export_route_module_changes_are_ascii`
    The touched router file remains ASCII (read
    `routers/me_router.py` and assert `.isascii()`).

Existing export and erase tests stay green and unedited.

## 7. R17 sabotage (required, and must be reported)

Exact temporary edit in the export handler: when calling
`execute_export`, pass a hostile user id taken from the query string
if present, for example
`user_id = request.query_params.get("user_id") or identity.user_id`,
and call `execute_export(user_id, backend)`.

`test_export_route_ignores_client_supplied_user_id` must fail (it
returns B's rows or mixes them). Other named tests should stay green
where they do not send a hostile query. Restore before the PR. If
in-place editing is blocked, an in-memory pytest plugin that wraps
the handler or `execute_export` is the accepted substitute. Drop the
plugin before the PR; no sabotage artifact may be committed.

## 8. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- an existing test fails for a reason related to this change;
- an existing test fails for any other reason not named in section 9;
- you feel you need to edit a file outside section 4;
- you are about to add nesting, a zip/file download, pagination,
  Auth delete, denylist, or cache purge to the export path;
- you are about to write a brief, a doc, or a second slice.

Never "fix" an unrelated failure, never skip or xfail a test, never
loosen an assertion, never force-push over another branch.

## 9. Gates

Run from the repo root, with `backend/.venv` if it exists. Use
`ruff==0.16.3` (CI pin). A newer ruff is not the gate.

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

Known pre-existing failures. These are not yours; do not touch them:

- `test_sparse_create_with_limited_hours_succeeds` (hard-coded date)
- `test_today_tonight_includes_venue_name` (fails near ICT midnight)

Anything else failing is yours until proven otherwise. Also confirm
touched files are ASCII only. If `ruff format --check .` fails on a
file you are not allowed to edit, stop and report; do not reformat it.

## 10. Out of scope (record as remainders, do not build)

- Nesting rows under trips; human-readable document; zip/PDF download
- Pagination or PostgREST range headers
- Wiring export for the in-memory `DatabaseService` path
- Auth delete, denylist, or cache purge on the export path
- Rate limiting the export route: the Gap 11 limiter counts only
  POST/PUT/PATCH/DELETE by design, so GET export is unthrottled until a
  separate limiter slice counts it for this path. Do not edit
  `monitoring/rate_limit.py` here.
- `cached_responses` SQL export (identity `none`, Gap 8 remainder)
- Tombstones, retention jobs, Flutter leave / local wipe
- Armor, Play Integrity, deploy, APK, hosted 0026

## 11. Delivery

1. Commit on `feat/spec43-g4-export-route` with the message:
   `SPEC-43 Gap 4 slice 14: GET /api/v1/me/export for the authenticated caller`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin feat/spec43-g4-export-route`), not from
   your local clone.
3. Do not merge, do not deploy, do not open or edit any other branch.
   This compute has no `gh`; the reviewer opens the PR from your
   branch. Do not try to work around that.

## 12. Report (exactly these fields, in this order)

1. Base `origin/main` SHA you started from.
2. Branch name and pushed SHA (verified from the remote).
3. `pytest` last line, and the name of every failing test.
4. `ruff check`, `ruff format --check`, `git diff --check` results
   (name the ruff version).
5. Files touched (must be only those in section 4).
6. For a successful export of A: HTTP status, table order, per-table
   row counts, and confirmation B's store counts are unchanged.
7. Confirmation that a request as A with `?user_id=B` still returns
   only A's rows.
8. Confirmation of the 501 and generic-500 paths, including that the
   canary string is absent from the 500 body and the WARNING log.
9. The R17 test that failed under sabotage, by name, confirmation
   other named tests stayed green where applicable, and confirmation
   the sabotage was removed.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
