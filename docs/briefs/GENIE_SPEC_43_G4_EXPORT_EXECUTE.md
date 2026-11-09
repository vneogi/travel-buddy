# Genie brief: SPEC-43 Gap 4 slice 11 -- walk the export plan against a backend

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27.

## Goal

Slice 10 landed the parent-first export plan (`2fa9074`, PR #188).
Slice 11 executes that plan against an injected backend. No SQL.
No FastAPI route. No live Postgres. The executor must call every
plan step in order, collect the fetched row lists, and stop on the
first backend error so a partial export is visible.

Acceptance: `execute_export(user_id, backend)` walks
`plan_export(user_id)` and invokes the matching backend method for
each step. A recording backend sees the same order as
`EXPORT_STEPS`. A failing step is the last call. Returned rows are
lists of dicts (copies), never mutated into the backend's store.

## Base

Latest `main` (`2fa9074`), including Gap 4 slice 10 (PR #188).

Create and push: `feat/spec43-g4-export-execute`

Do not merge. Do not deploy. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/data_rights_export.py` (`EXPORT_STEPS`, `plan_export`,
  `EXPORT_METHODS`, `METHOD_FOR_IDENTITY`)
- `services/data_rights_erase.py` (`execute_erase` shape to mirror)
- `tests/test_spec43_g4_erase_execute.py` (test shape to mirror)
- `tests/test_spec43_g4_export_plan.py` (must stay green)

No new migration. No Flutter. No live Postgres. No network.
Do not import litellm, supabase, httpx, psycopg, or psycopg2.
Do not add a router. Do not change RIGHTS_MAP (export stays
`"planned"`). Do not change the erase modules.

## Scope

### 1. Extend `services/data_rights_export.py`

Keep stdlib + `config.data_rights` only. ASCII only.

- `ExportBackend` Protocol with three methods, each taking
  `user_id: str` and `table: str` and returning `List[dict]`
  (zero or more row dicts; the fake may return `[]`):
  - `fetch_where_user_id`
  - `fetch_via_trip_states`
  - `fetch_via_party`
- `UnknownExportMethodError(ValueError)` if a step.method is not
  one of those three.
- `execute_export(user_id: str, backend: ExportBackend,
  steps: Optional[Iterable[dict]] = None) -> List[dict]`:
  1. `default_plan = plan_export(user_id)` (blank user_id still
     ValueError from plan_export; do not call the backend).
  2. `plan = default_plan if steps is None else list(steps)`.
  3. Validate every step.method is in `EXPORT_METHODS` before any
     backend call; else raise `UnknownExportMethodError`.
  4. For each step, getattr the method name and call
     `method(user_id=user_id, table=step["table"])`.
  5. Append a result dict
     `{table, method, via, rows}` where `rows` is a **new list** of
     **shallow-copied** dicts from the backend return (so mutating
     the result never mutates the backend's store). Coerce with
     `[dict(r) for r in returned]`.
  6. If a backend method raises, do not call later steps. Re-raise
     the same exception. Do not return partial results.
  7. Return the result list on full success.

Do not log user_id. Do not print. Do not open files or sockets.
Do not write SQL strings. Do not nest rows under trips this slice
(flat per-table lists only).

`cached_responses` and catalog tables stay unexecuted because they
are not in `EXPORT_STEPS`.

Do not implement an in-memory or Postgres export backend this slice.

### 2. Named tests

New file `tests/test_spec43_g4_export_execute.py`. No network.

Use a `RecordingBackend` that records `(method_name, user_id, table)`
and returns a one-row list `[{"seed": table}]` (or empty when asked).

Exact names:

- `test_execute_export_calls_backend_in_plan_order`
  Calls match `EXPORT_STEPS` tables and methods; every call uses the
  same user_id; `cached_responses` absent; results shape is
  `{table, method, via, rows}` with `rows == [{"seed": table}]`.
- `test_execute_export_stops_after_first_backend_error`
  Fail on `trip_node` (third step) with
  `RuntimeError("EXPORT-CANARY-g4-stop")`. Only `user_tiers` and
  `trip_states` and `trip_node` are called; later tables are not.
  Same exception object re-raised.
- `test_execute_export_rejects_blank_user_id_before_backend`
- `test_execute_export_unknown_method_before_any_backend_call`
- `test_execute_export_result_rows_are_detached_copies`
  Backend returns a mutable dict; mutating the result's row must not
  change the backend's returned object (and vice versa if the
  backend keeps a reference).
- `test_execute_export_accepts_explicit_steps_override`
  A one-step custom plan calls only that method/table.
- `test_export_execute_module_has_no_supabase_import`

The export-plan and erase-execute tests stay green and unchanged.

### 3. R17 sabotage

Exact edit: in `execute_export`, after a successful backend call,
continue to the next step even when building results -- specifically,
skip appending the result for `trip_states` (or drop `trip_states`
from the returned list).

`test_execute_export_calls_backend_in_plan_order` must fail (missing
`trip_states` in results while the backend was still called, or
results length wrong). Pair it with a second failure by also
skipping the backend call for `trip_states` so
`test_execute_export_calls_backend_in_plan_order` fails on call
order; OR sabotage by not stopping on error so
`test_execute_export_stops_after_first_backend_error` fails.

Preferred single edit that fails both required tests: remove the
`if backend raises: re-raise` behaviour and instead `continue` after
logging nothing -- that fails the stop-on-error test; also skip
appending `trip_states` results to fail the order/shape test.

Simpler accepted pair: (1) do not re-raise on backend error (swallow
and continue) and (2) omit `trip_states` from returned results.
Restore before the PR. If Databricks blocks in-place sabotage, an
in-memory pytest plugin that wraps `execute_export` is the accepted
substitute. Drop the plugin before the PR.

Named tests that must fail under R17:

- `test_execute_export_calls_backend_in_plan_order`
- `test_execute_export_stops_after_first_backend_error`

## Out of scope (record as remainders, do not build)

- In-memory or Supabase export backend
- HTTP `GET`/`POST /api/v1/me/export`
- Nesting / human-readable document formatting
- `cached_responses` SQL export
- Tombstones, retention jobs, Flutter, shared denylist
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

SHA, branch, pytest last line, files touched, the recorded
`(method, table)` call list for a full successful run, and the
result tables list. Name the two R17 tests that failed. Named tests
in the report must include
`test_execute_export_calls_backend_in_plan_order` and
`test_execute_export_stops_after_first_backend_error`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
