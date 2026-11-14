# Genie brief: SPEC-43 Gap 4 slice 19 -- wire nested document into GET /api/v1/me/export

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

Gap 4 export is on main: flat `GET /api/v1/me/export` (slice 14) and a
pure nested document builder `build_export_document` (slice 18). The
HTTP route still returns only the flat `{status, tables}` shape. This
slice wires the nested document into that route behind an explicit
query parameter so the existing flat contract stays intact for current
clients and tests. No zip, no PDF, no pagination, no SQL.

## 1. Goal and the properties that matter

1. Default `GET /api/v1/me/export` (no `format`, or `format=tables`)
   still returns the flat `{status: "exported", tables: [...]}`
   response. Every existing export-route assertion must stay green
   without editing those tests.
2. `GET /api/v1/me/export?format=document` returns the nested document
   from `build_export_document`, wrapped as
   `{status: "exported", document: <nested>}` for the authenticated
   caller only.
3. The user id still comes only from `resolve_identity`. Query/body
   `user_id` must not change whose rows are exported.
4. Failure shape is unchanged: 501 when no Supabase backend; 500
   `{"detail": "export_incomplete"}` on any exception from
   `execute_export` or `build_export_document` (including its
   ValueError), with one WARNING naming the exception class and
   request id only.
5. Invalid `format` values return 422. Do not invent other formats.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `routers/me_router.py`, `services/data_rights_export.py`,
   `services/data_rights_export_document.py`,
   `services/data_rights_export_supabase.py`,
   `tests/test_spec43_g4_export_route.py`,
   `tests/test_spec43_g4_export_document.py`,
   `docs/ENGINEERING_RULES.md`.
3. Confirm `tests/test_spec43_g4_export_route_document.py` does NOT
   exist, and `origin/feat/spec43-g4-export-route-document` does not
   exist. If either exists, stop and report.
4. Create a fresh branch from that main:
   `feat/spec43-g4-export-route-document`.

Never start work from an older SHA. Check the base before you write a
line.

## 3. Read before editing (read only; these are your patterns)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16 (no hard-coded pytest
  totals in docs), R17.
- `routers/me_router.py`: the current `export_me` handler,
  `ExportResponse` / `ExportedTable`, `get_export_backend`, and the
  erase route's generic-500 pattern.
- `services/data_rights_export_document.py`: `build_export_document`,
  `count_rows`, required keys (`format`, `version`, `account`,
  `trips`, `unattached`).
- `tests/test_spec43_g4_export_route.py`: TestClient, fake client,
  debug-header auth, canary failure, hostility `?user_id=`. Do not
  edit this file.
- `tests/test_spec43_g4_export_document.py`: seed helper and
  conservation checks to mirror for the HTTP document path.

## 4. Files you may touch

- `routers/me_router.py` (export path only: query param, response
  models, handler; leave erase behaviour unchanged)
- `tests/test_spec43_g4_export_route_document.py` (new)

Nothing else. In particular do NOT change:

- `tests/test_spec43_g4_export_route.py` or any other existing test
- `services/data_rights_export_document.py`,
  `services/data_rights_export.py`,
  `services/data_rights_export_memory.py`,
  `services/data_rights_export_supabase.py`
- any erase / tombstone / denylist / cache-purge module
- `monitoring/rate_limit.py`, `tests/conftest.py`, `main.py`,
  `security.py`, `config/data_rights.py`
- any SQL or migration
- `mobile/**`, requirements, any doc, any brief

Do not write a new brief or any doc. Do not start slice 20.

## 5. The route change: `routers/me_router.py`

### 5.1 Query parameter

Add an optional query parameter to `export_me`:

- Name: `format`
- Allowed values: `tables` (default when omitted) and `document`
- Anything else: FastAPI/Pydantic 422 (use a `Literal["tables", "document"]`
  with default `"tables"`, or an equivalent that yields 422 on bad
  input). Do not accept aliases like `nested` or `json`.

### 5.2 Response models

Keep `ExportResponse` for the flat shape (`status` + `tables`).

Add a second response model for the document shape, for example
`ExportDocumentResponse` with:

- `status: Literal["exported"]`
- `document: dict` (the nested object from `build_export_document`)

`extra="forbid"` on request wrappers you add. For the response, forbid
extra top-level keys beyond `status` and `document`.

Because the two success bodies differ, either:

- use a Union response model / `response_model=None` with explicit
  returns, or
- return `JSONResponse` / plain dicts that match the shapes above.

Do not return both `tables` and `document` in one body. Flat stays
flat; document stays document.

### 5.3 Handler behaviour

1. Call `execute_export(identity.user_id, backend)` as today.
2. If `format == "tables"`: return the existing flat body
   (`status` + `tables` without `method`/`via`).
3. If `format == "document"`: call
   `build_export_document(results)` and return
   `{"status": "exported", "document": <that object>}`.
4. On any exception from either call: same WARNING + 500
   `export_incomplete` path as today. A `ValueError` from the
   builder is an incomplete export, not a 422.
5. Still no Auth delete, denylist, cache purge, or user creation.

### 5.4 Module docstring

Update the export notes in the module docstring:

- Mention `?format=document` returns the nested document from
  slice 18; default remains flat tables.
- Fix the stale sentence that says GET export is unthrottled: Gap 4
  slice 16 counts `GET /api/v1/me/export`. Say that plainly.
- Leave erase documentation intact.

ASCII only. No drive-by refactors of erase helpers.

## 6. Tests: `tests/test_spec43_g4_export_route_document.py`

No network. No `supabase` package. Copy the read-only fake client and
seed pattern from `tests/test_spec43_g4_export_route.py` (do not
import across test files). Auth via `X-Debug-User-Id`. Override
`get_export_backend` with `SupabaseExportBackend(fake)`. Use
`TestClient(app, raise_server_exceptions=False)`.

Exact test names (each must exist; add more only if they add proof):

1. `test_export_document_format_returns_nested_document_for_caller_only`
   `GET /api/v1/me/export?format=document` as A. Status 200.
   Body keys exactly `{"status", "document"}`. `status == "exported"`.
   Document has `format == "travel-buddy-export"`, `version == 1`,
   `account`, `trips`, `unattached`. Every row's test-only
   `seed_owner` is A. Response text does not contain B's user id.
   B's store counts unchanged.

2. `test_export_document_format_conserves_rows`
   Same request. Import `count_rows` from
   `services.data_rights_export_document`. `count_rows(document)`
   equals A's per-table seed counts (derive from the fake store /
   `seed_owner`; no hard-coded totals). With the two-user seed,
   `unattached` lists are empty.

3. `test_default_and_tables_format_still_return_flat_shape`
   `GET` with no query, and `GET ?format=tables`, both as A.
   Each body has keys exactly `{"status", "tables"}` (no
   `document`). Table order follows `EXPORT_STEPS`. This proves the
   existing contract without editing the old test file.

4. `test_export_document_ignores_client_supplied_user_id`
   Authenticated as A, `?format=document&user_id=B` (and a body
   `user_id` if you try one). Document rows are only A's. B
   untouched. This is the R17 hostility test.

5. `test_export_document_requires_authentication`
   No auth, `?format=document` -> 401. Fake store unchanged / no
   reads (empty ops, same as the flat auth test).

6. `test_export_document_invalid_format_is_422`
   `?format=nested` and `?format=` -> 422. Fake ops empty (or no
   export executed).

7. `test_export_document_builder_failure_is_generic_500`
   Monkeypatch `build_export_document` to raise
   `ValueError("DOC-CANARY-g4-route")` when `format=document`.
   Expect 500 `{"detail": "export_incomplete"}`. Canary, user ids,
   and table names absent from the body. Caplog: one WARNING on
   `travelbuddy` with the exception class name and a request id;
   canary absent from the log message. Capsys empty of the canary.

8. `test_export_document_execute_failure_still_generic_500`
   Same canary pattern as the flat route, but with
   `?format=document` and a mid-plan table failure on the fake.
   Still 500 `export_incomplete`, canary not in body or WARNING
   message.

9. `test_export_document_returns_501_when_no_supabase_backend`
   Monkeypatch `IS_SUPABASE` False, clear the dependency override,
   `?format=document` -> 501 `export_unavailable`.

10. `test_export_document_route_module_is_ascii`
    Read `routers/me_router.py` and assert `.isascii()`.

Existing export-route tests stay green and unedited.

## 7. R17 sabotage (required, and must be reported)

Exact temporary edit: in the `format=document` branch, pass a hostile
user id from the query string into `execute_export` when present
(same idea as slice 14): for example
`user_id = request.query_params.get("user_id") or identity.user_id`.

`test_export_document_ignores_client_supplied_user_id` must fail (it
returns B's rows or mixes them). Restore before the PR. If in-place
editing is blocked, an in-memory pytest plugin that wraps the
handler or `execute_export` is the accepted substitute. Drop the
plugin before the PR; no sabotage artifact may be committed.

## 8. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- an existing test fails for a reason related to this change
  (especially any test in `test_spec43_g4_export_route.py`);
- an existing test fails for any other reason not named in section 9;
- you feel you need to edit a file outside section 4;
- you are about to change the default response away from flat tables;
- you are about to add zip, PDF, Content-Disposition, pagination,
  Auth delete, denylist, or cache purge;
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

Anything else failing is yours until proven otherwise. Confirm touched
files are ASCII only. If `ruff format --check .` fails on a file you
are not allowed to edit, stop and report; do not reformat it.

Dart / Flutter checks are not part of this slice. Do not run them.

## 10. Out of scope (record as remainders, do not build)

- Zip, PDF, Content-Disposition download, pagination
- Making nested the default (needs a coordinated client change)
- Durable tombstone table / erase-route hook (blocked on 0026 +
  `rolbypassrls`)
- Retention jobs
- Flutter leave / local wipe
- Armor, Play Integrity, deploy, APK, hosted 0026
- Frontend findings F1-F4 in `UX_BACKLOG.md`

## 11. Delivery

1. Commit on `feat/spec43-g4-export-route-document` with the message:
   `SPEC-43 Gap 4 slice 19: wire nested document into GET /api/v1/me/export`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin feat/spec43-g4-export-route-document`),
   not from your local clone.
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
6. For `?format=document` as A: HTTP status, top-level keys, document
   `format`/`version`, trip count, and confirmation B's id is absent.
7. Confirmation that default and `?format=tables` still return flat
   `{status, tables}` only.
8. Confirmation of 422 for bad format, and of the document-path
   generic 500 (canary absent from body and WARNING text).
9. The R17 test that failed under sabotage, by name, confirmation
   other named tests stayed green where applicable, and confirmation
   the sabotage was removed.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
