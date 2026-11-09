# Genie brief: SPEC-43 Gap 4 slice 2 -- erase plan walks the inventory

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27. Read Gap 4 of
`docs/specs/SPEC-43-security-privacy-and-data-governance.md` and
SPEC-27 data-rights items 7-8 only (schema-walking deletion).

## Goal

Slice 1 landed the inventory (`cd28bf3`, PR #170). Slice 2 adds
the erase *plan*: every identity-bearing table in RIGHTS_MAP
must have an ordered erase step, and a new identity table
without a step fails a named test. No database is touched. No
endpoint. No tombstone. No export document.

Acceptance for this slice: `plan_erase(user_id)` returns an
ordered list of steps covering every table whose
`RIGHTS_MAP[t]["identity"] != "none"`, children before parents,
and a synthetic identity table without a step fails the guard.

## Base

Latest `main` (`cd28bf3`), including Gap 4 slice 1
`cd28bf3` (PR #170).

Create and push: `feat/spec43-g4-erase-plan`

Do not merge. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `config/data_rights.py` (`RIGHTS_MAP`, `IDENTITY_COLUMNS`,
  `identity_tables`, `walk_created_tables`)
- `tests/test_spec43_g4_rights_inventory.py` (must stay green;
  do not edit unless a shared constant must move)
- `supabase/migrations/0026_spec43_g2_rls.sql` (join shapes for
  via_trip_states / via_party only; do not edit)

No new migration. No Flutter. No live Postgres. No network.
Do not import litellm, supabase, or httpx.

## Scope

### 1. Module `services/data_rights_erase.py`

Standard library + `config.data_rights` only. ASCII only.

- `ERASE_REQUIRED`: frozenset of table names where
  `RIGHTS_MAP[t]["identity"] != "none"`. Build it from
  RIGHTS_MAP at import time; do not hand-list the seven names.
- `ERASE_STEPS: tuple[dict, ...]`: one dict per required table,
  in erase order (dependents first). Each dict has exactly:
  - `table`: str
  - `method`: one of
    `"delete_where_user_id"`,
    `"delete_via_trip_states"`,
    `"delete_via_party"`
  - `via`: `None` for direct; `"trip_states.trip_id"` for
    via_trip_states; `"trip_party.party_id->trip_states"` for
    via_party
  - `note`: one short ASCII sentence

  Method must match RIGHTS_MAP identity:
  - `direct_user_id` -> `delete_where_user_id`
  - `via_trip_states` -> `delete_via_trip_states`
  - `via_party` -> `delete_via_party`

  Required order constraints (asserted by tests):
  - `party_member` before `trip_party`
  - `trip_party`, `trip_node`, `trip_edge`, `trip_command`,
    `signal`, `event_log` before `trip_states`
  - `user_tiers` may be anywhere relative to trip tables, but
    must appear exactly once

- `missing_erase_steps(rights=RIGHTS_MAP, steps=ERASE_STEPS) -> set[str]`:
  required tables minus tables named in steps.
- `extra_erase_steps(rights=RIGHTS_MAP, steps=ERASE_STEPS) -> set[str]`:
  tables in steps that are not required (catalog / none must
  not appear).
- `plan_erase(user_id: str) -> list[dict]`:
  returns a new list of step dicts, each copy including
  `"user_id": <the argument>`. Do not hit a database. Do not
  log the user_id beyond returning it in the plan structure.
  Reject empty / None user_id with ValueError.

Do not execute SQL. Do not open connections. Do not write files.

`cached_responses` stays out of ERASE_STEPS this slice (identity
is `none`; Gap 8 SQL path is a later remainder). Catalog tables
stay out.

### 2. Named tests

New file `tests/test_spec43_g4_erase_plan.py`. No network.

Exact names:

- `test_every_identity_table_has_an_erase_step`
  (`missing_erase_steps()` empty)
- `test_no_erase_steps_for_none_identity_tables`
  (`extra_erase_steps()` empty; `cached_responses` not in steps)
- `test_erase_step_method_matches_rights_identity`
- `test_erase_order_deletes_children_before_trip_states`
  (assert the index constraints listed above)
- `test_plan_erase_includes_user_id_on_every_step`
- `test_plan_erase_rejects_blank_user_id`
- `test_synthetic_identity_table_without_step_is_detected`:
  build a rights dict that copies RIGHTS_MAP and adds
  `synthetic_identity` with `identity="direct_user_id"` and
  planned export/delete/retention; assert
  `missing_erase_steps(rights=that, steps=ERASE_STEPS)`
  contains `synthetic_identity`. Do not add it to ERASE_STEPS
  or RIGHTS_MAP.

Inventory tests stay green. Do not edit migrations.

### 3. R17 sabotage

Exact edit: remove the `trip_states` step from `ERASE_STEPS`.

`test_every_identity_table_has_an_erase_step` must fail
(`trip_states` missing). Restore before the PR. If Databricks
blocks in-place sabotage, an in-memory pytest plugin that
rebuilds `ERASE_STEPS` without that table is the accepted
substitute. Drop the plugin before the PR.

## Out of scope

- Any DELETE SQL, Supabase client call, or FastAPI route
- Export document / endpoint
- Tombstones, backup restore, retention jobs
- Local SQLCipher wipe (Gap 5 already has sign-out wipe)
- Alias credential tables (SPEC-24 merge not on main as tables)
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
`table:method` list from ERASE_STEPS. Named tests in the report
must include `test_every_identity_table_has_an_erase_step` and
`test_synthetic_identity_table_without_step_is_detected`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
