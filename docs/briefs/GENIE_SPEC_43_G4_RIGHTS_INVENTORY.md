# Genie brief: SPEC-43 Gap 4 slice 1 -- data-rights inventory guard

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md`. Do not re-read all of
SPEC-43 or SPEC-27. Read the Gap 4 section of
`docs/specs/SPEC-43-security-privacy-and-data-governance.md` only.

## Goal

Gap 4 says deletion and export must cover every identity-bearing
table, and a new identity table must fail a test until export and
deletion handle it. Slice 1 builds only the inventory and the
guard. It does not build any endpoint, delete, export, tombstone,
or retention job.

Acceptance for this slice: every table created by
`supabase/migrations/*.sql` has an explicit rights classification,
and a synthetic new identity table fails the guard.

## Base

Latest `main` (`704c503`), including Gap 3 closed: fallback pin
`8d8b28b` (PR #165) and embedding failure log `704c503`
(PR #168).

Create and push: `feat/spec43-g4-rights-inventory`

Do not merge. Open one PR after gates are green.

## Read before editing

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `docs/specs/SPEC-43-security-privacy-and-data-governance.md`,
  Gap 4 section only
- `tests/test_spec43_g2_rls.py` (`PERSONAL_TABLES`,
  `CATALOG_TABLES`, `test_every_migration_table_is_classified`).
  Its create-table regex is the pattern to reuse. Do not edit
  this file; it must stay green.
- `supabase/migrations/` (read the CREATE TABLE statements and
  their identity columns; do not edit any migration)

No new migration. No `CREATE TABLE` in any file you add. No
Flutter. No live Postgres. No hosted Supabase. No network.

## Scope

### 1. Module `config/data_rights.py`

Pure Python, no imports from the app beyond the standard library.

- `walk_created_tables(migrations_dir) -> set[str]`: read
  `*.sql` in filename order, strip `--` comments and `/* */`
  comments, collect `CREATE TABLE [IF NOT EXISTS] name`, and
  remove any name later dropped by `DROP TABLE [IF EXISTS] name`.
  Lowercase names. Current migrations have 18 CREATE TABLE
  statements and no DROP TABLE; the walker must not assume that.
- `identity_tables(migrations_dir) -> set[str]`: a created table
  whose CREATE body (balanced parentheses, not a regex to the
  next semicolon) names a column `user_id`, `party_id`,
  `identity_id`, or `owner_id`. Use the same column list in code
  and in the test. Do not hand-pick tables.
- `RIGHTS_MAP: dict[str, dict]`: one entry per created table with
  exactly these keys:
  - `identity`: one of `"direct_user_id"`, `"via_trip_states"`,
    `"via_party"`, `"none"`
  - `export`: `"planned"` (slice 1 only allows this value)
  - `delete`: `"planned"` (slice 1 only allows this value)
  - `retention`: `"planned"` or `"not_applicable"`
  - `note`: one short ASCII sentence naming the identity column
    or why there is none

Derive `identity` from the actual migrations. A table that
`identity_tables` returns must not be `"none"`. A table whose
owner is only reachable through a parent (for example
`trip_node` via `trip_states`) is `"via_trip_states"`, and the
note names the join. Do not guess; read the CREATE TABLE and
the 0026 policy text if needed.

- `unclassified(created: set[str], rights: dict) -> set[str]`:
  `created - set(rights)`.
- `stale(created: set[str], rights: dict) -> set[str]`:
  `set(rights) - created`.

Keep ASCII only in the module.

### 2. Named tests

New file `tests/test_spec43_g4_rights_inventory.py`. No network.
Use `REPO_ROOT / "supabase" / "migrations"` and `tmp_path`.

Required test names (exact):

- `test_every_migration_table_has_rights_classification`
  (`unclassified(...)` empty on the real migrations)
- `test_no_stale_rights_entries`
  (`stale(...)` empty)
- `test_identity_tables_are_not_classified_none`
  (for every table in `identity_tables(...)`, `identity != "none"`)
- `test_slice_one_only_plans_export_and_delete`
  (every entry has `export == "planned"` and `delete == "planned"`;
  `retention` is in the allowed set)
- `test_synthetic_identity_table_is_unclassified`
  Copy the real migrations into `tmp_path`, add
  `9999_synthetic_identity.sql` containing
  `CREATE TABLE synthetic_identity (id uuid primary key, user_id uuid not null);`,
  then assert `"synthetic_identity"` is in
  `unclassified(walk_created_tables(tmp), RIGHTS_MAP)` and in
  `identity_tables(tmp)`. Do not add it to `RIGHTS_MAP`.
- `test_walker_respects_drop_table(tmp_path)`
  Two temp migrations: one creates `scratch_table`, a later one
  drops it. Assert it is absent from `walk_created_tables`.

Do not weaken or edit `tests/test_spec43_g2_rls.py`.

### 3. R17 sabotage

Exact edit: delete the `trip_states` entry from `RIGHTS_MAP`.

`test_every_migration_table_has_rights_classification` must fail
(`trip_states` is unclassified). Restore before the PR. If
Databricks blocks in-place sabotage, an in-memory pytest plugin
that removes that key from the imported map is the accepted
substitute. Drop the plugin before the PR.

## Out of scope

- Any export or deletion endpoint, client flow, or local clearing
- Deletion tombstones, backup restore drill, retention jobs
- Product retention durations (counsel-owned; keep `retention`
  as `"planned"` or `"not_applicable"` only)
- Changing any migration or RLS policy
- `cached_responses` SQL path wiring (Gap 8 remainder)
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

SHA, branch, pytest last line, files touched, and the list of
created tables with their `identity` value (one line each).
Named tests in the report must include
`test_every_migration_table_has_rights_classification` and
`test_synthetic_identity_table_is_unclassified`. Do not merge.
Do not edit this brief, PROJECT_STATUS, or HANDOFF.
