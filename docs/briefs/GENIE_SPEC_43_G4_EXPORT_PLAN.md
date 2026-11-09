# Genie brief: SPEC-43 Gap 4 slice 10 -- export plan

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27.

## Goal

Slices 1-9 closed the server erase path (inventory through in-process
cache purge). Gap 4 still has no export. Slice 10 adds the ordered
export plan over the same identity tables the erase plan covers:
every RIGHTS_MAP table whose identity is not "none" gets exactly one
export step, with a fetch method derived from that identity.

Parents come first (unlike erase), so a later document builder can
nest trip children under trips. Pure data. No SQL, no backend, no
route, no network.

## Base

Latest `main` (`004ed6a`), including Gap 4 slice 9 (PR #186).

Create and push: `feat/spec43-g4-export-plan`

Do not merge. Do not deploy. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `config/data_rights.py` (`RIGHTS_MAP`, identity values)
- `services/data_rights_erase.py` (plan shape to mirror: steps,
  method mapping, missing/extra helpers, `plan_erase`)
- `tests/test_spec43_g4_erase_plan.py` (test shape to mirror)
- Do not change the erase modules or RIGHTS_MAP entries this slice
  (export stays `"planned"` until a later slice marks it live).

No migration. No Flutter. No route. No Supabase client. Do not deploy.

## Scope

### 1. `services/data_rights_export.py`

ASCII only. Standard library plus `config.data_rights`. No logging,
no print, no supabase import.

Mirror the erase module's structure:

- `METHOD_FOR_IDENTITY`:
  - `direct_user_id` -> (`fetch_where_user_id`, None)
  - `via_trip_states` -> (`fetch_via_trip_states`, `trip_states.trip_id`)
  - `via_party` -> (`fetch_via_party`, `trip_party.party_id->trip_states`)
- `EXPORT_METHODS`, `STEP_KEYS` = `{table, method, via, note}`
- `required_tables` / `EXPORT_REQUIRED`: identity != `"none"`
  (same set as `ERASE_REQUIRED`; assert that in tests by importing
  both, do not hard-code a count).
- `EXPORT_STEPS`: exactly one step per required table. **Parent-first
  order** (the inverse concern of erase):

  1. `user_tiers`
  2. `trip_states`
  3. `trip_node`
  4. `trip_edge`
  5. `trip_party`
  6. `party_member` (after `trip_party`)
  7. `trip_command`
  8. `signal`
  9. `event_log`

  Each note is one ASCII line, no newlines.
- `missing_export_steps` / `extra_export_steps` (same semantics as
  erase).
- `plan_export(user_id) -> List[dict]`: copies of each step plus
  `user_id`. Blank / non-string / whitespace-only -> `ValueError`
  before building. Mutating the returned plan must not change
  `EXPORT_STEPS`.

Do not implement `execute_export` or any backend Protocol this slice.

### 2. Named tests

New file `tests/test_spec43_g4_export_plan.py`. Pure data. No network.

Exact names:

- `test_export_required_matches_erase_required`
- `test_every_identity_table_has_an_export_step`
- `test_no_export_steps_for_none_identity_tables`
  (`cached_responses` and catalog tables absent)
- `test_each_table_has_exactly_one_export_step`
- `test_export_step_method_matches_rights_identity`
- `test_export_order_is_parents_before_children`
  (`user_tiers` and `trip_states` before trip children;
  `trip_party` before `party_member`)
- `test_plan_export_includes_user_id_on_every_step`
- `test_plan_export_rejects_blank_user_id`
- `test_synthetic_identity_table_without_export_step_is_detected`
- `test_export_module_has_no_supabase_import`

The Gap 4 erase-plan tests stay green and unchanged.

### 3. R17 sabotage

Exact edit: remove the `trip_states` step from `EXPORT_STEPS` (or
rename its table to something absent from RIGHTS_MAP).

`test_every_identity_table_has_an_export_step` and
`test_export_required_matches_erase_required` (or
`test_export_order_is_parents_before_children` if the rename path
breaks order) must fail. Restore before the PR. If Databricks blocks
in-place sabotage, an in-memory pytest plugin that mutates
`EXPORT_STEPS` for the session is the accepted substitute. Drop the
plugin before the PR.

## Out of scope (record as remainders, do not build)

- `execute_export` and any ExportBackend
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

SHA, branch, pytest last line, files touched, the ordered table list
from `EXPORT_STEPS`, and confirmation that `EXPORT_REQUIRED ==
ERASE_REQUIRED`. Name the two R17 tests that failed. Named tests in
the report must include `test_export_required_matches_erase_required`
and `test_export_order_is_parents_before_children`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
