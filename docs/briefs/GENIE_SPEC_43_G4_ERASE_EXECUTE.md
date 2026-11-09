# Genie brief: SPEC-43 Gap 4 slice 3 -- walk the erase plan against a backend

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27. Read Gap 4 of
`docs/specs/SPEC-43-security-privacy-and-data-governance.md`
only as needed.

## Goal

Slice 2 landed the ordered plan (`f387c55`, PR #172). Slice 3
executes that plan against an injected backend. No SQL is
written. No FastAPI route. No live Postgres. The executor must
call every plan step in order and stop on the first backend
error so a partial erase is visible.

Acceptance: `execute_erase(user_id, backend)` walks
`plan_erase(user_id)` and invokes the matching backend method
for each step. A recording backend sees the same order as
`ERASE_STEPS`. A failing step is the last call.

## Base

Latest `main` (`f387c55`), including Gap 4 slice 2
`f387c55` (PR #172).

Create and push: `feat/spec43-g4-erase-execute`

Do not merge. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/data_rights_erase.py` (`ERASE_STEPS`, `plan_erase`,
  `METHOD_FOR_IDENTITY`)
- `config/data_rights.py` (`RIGHTS_MAP`)
- `tests/test_spec43_g4_erase_plan.py` (must stay green)
- `tests/test_spec43_g4_rights_inventory.py` (must stay green)

No new migration. No Flutter. No live Postgres. No network.
Do not import litellm, supabase, httpx, psycopg, or psycopg2.
Do not add a router.

## Scope

### 1. Extend `services/data_rights_erase.py`

Keep stdlib + `config.data_rights` only. ASCII only.

- `EraseBackend` Protocol (typing.Protocol) with three methods,
  each taking `user_id: str` and `table: str` and returning
  `int` (rows affected; the fake may return 0):
  - `delete_where_user_id`
  - `delete_via_trip_states`
  - `delete_via_party`
- `UnknownEraseMethodError(ValueError)` if a step.method is
  not one of those three.
- `execute_erase(user_id: str, backend: EraseBackend) -> list[dict]`:
  1. `plan = plan_erase(user_id)` (blank user_id still
     ValueError from plan_erase; do not call the backend).
  2. For each step, getattr the method name and call
     `method(user_id=user_id, table=step["table"])`.
  3. Append a result dict `{table, method, via, rows}` using
     the int return.
  4. If a backend method raises, do not call later steps.
     Re-raise the same exception. Results already collected
     are not returned (raise, do not swallow).
  5. Return the result list on full success.

Do not log user_id. Do not print. Do not open files or
sockets. Do not write SQL strings.

`cached_responses` and catalog tables stay unexecuted because
they are not in `ERASE_STEPS`.

Do not implement a Postgres backend this slice.

### 2. Named tests

New file `tests/test_spec43_g4_erase_execute.py`. No network.

A recording backend in the test file stores
`(method_name, user_id, table)` tuples and returns 1.

Exact names:

- `test_execute_erase_calls_backend_in_plan_order`
  Call `execute_erase` with a recording backend. Assert
  `[table for ...]` equals `[s["table"] for s in ERASE_STEPS]`
  and each method name matches the step. `cached_responses`
  is never called.
- `test_execute_erase_stops_after_first_backend_error`
  Backend raises `RuntimeError("ERASE-CANARY-g4-stop")` on
  `trip_party` (the second step). Assert the exception
  propagates, calls are exactly `party_member` then
  `trip_party`, and later tables including `trip_states`
  are not called.
- `test_execute_erase_rejects_blank_user_id_before_backend`
  Blank/None never reaches the backend (calls list empty).
- `test_execute_erase_unknown_method_does_not_call_backend`
  Monkeypatch a copy of one step with `method="delete_everywhere"`.
  Assert `UnknownEraseMethodError` and zero backend calls.
  Restore ERASE_STEPS / plan_erase after (or pass a local
  steps list if you add an optional `steps=` argument to
  `execute_erase`; optional `steps=` defaulting to
  `plan_erase(user_id)` is allowed).
- `test_recording_backend_never_sees_catalog_tables`

Inventory and plan tests stay green. Do not edit migrations.

### 3. R17 sabotage

Exact edit: in `execute_erase`, skip the step whose
`table == "trip_states"` (continue without calling the
backend).

`test_execute_erase_calls_backend_in_plan_order` must fail
(`trip_states` absent from the call list). Restore before
the PR. If Databricks blocks in-place sabotage, an
in-memory pytest plugin that wraps `execute_erase` and
drops that call is the accepted substitute. Drop the
plugin before the PR.

## Out of scope

- Any DELETE SQL, Supabase client, or FastAPI route
- Export document / endpoint
- Tombstones, backup restore, retention jobs
- Local SQLCipher wipe
- Armor, Play Integrity, Flutter, deploy, APK, hosted 0026

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.
Do not "fix" `test_today_tonight_includes_venue_name` or
`test_sparse_create_with_limited_hours_succeeds`.

## Report

SHA, branch, pytest last line, files touched, and the ordered
backend call list from the named order test. Named tests in
the report must include
`test_execute_erase_calls_backend_in_plan_order` and
`test_execute_erase_stops_after_first_backend_error`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
