# Genie brief: SPEC-43 Gap 10 -- drop expired in-memory error-ring entries

Landed on `main` as `12588c2` (PR #153). Do not re-implement this
slice. Remainder: GCP log-bucket retention (owner), not more
in-process ring work. Do not start Cloud Logging, Armor, Play
Integrity, SQL cache, `derived_feature`, hosted 0026, Flutter,
deploy, or an APK without a new brief.

Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md` (Who you are, Who else
is, How a slice moves, Hard stops). Do not re-read all of
SPEC-43. Do not start Cloud Logging, regional buckets, access
audit, Armor, Play Integrity, SQL cache, `derived_feature`,
hosted 0026, Flutter, deploy, or an APK.

## Goal

`ErrorLog` keeps up to 100 redacted entries until process
restart, cap eviction, or DELETE `/api/v1/debug/errors`. There
is no TTL. A redacted traceback (path, request_id, exception
text) can sit in process memory for the life of a Cloud Run
instance.

Gap 10 remainder after IAM: **in-process retention**. This is
not GCP log-bucket retention. Do not add Cloud Logging sinks,
GCS, or IAM audit.

Read before editing:

- `docs/ENGINEERING_RULES.md` (R14, R17)
- `monitoring/error_log.py`
- `routers/debug_router.py` (GET uses `recent` + `count`)
- `tests/test_spec43_g10_iam.py` (must stay green; do not edit)
- `tests/test_spec43_g10_logs.py` (must stay green; do not edit)
- `tests/test_observability.py` (`test_ring_buffer_capped_at_100`)

Base branch: latest `main` (`af4227b`), including Gap 10 IAM
part B `17fb0e4` (PR #150).

Create and push: `feat/spec43-g10-retention`

Do not merge. Open one PR after the gates are green.

## Why this exists

Cap-100 is a size bound, not a time bound. Same shape as Gap 8
cache: skip/list is not deletion. Debug GET still returns old
rows. `record` of a new crash does not drop yesterday's.

Do not add a background thread or lifespan loop. Call purge on
the live paths.

## Current production seams to reuse

- Keep redaction, truncation, maxlen 100, IAM on the debug
  router, Cloud Run debug refuse, 422 stripping.
- Keep `ts` as UTC ISO from `datetime.now(tz=timezone.utc).isoformat()`.
- Do not persist the ring to disk or Postgres.
- Do not log dropped entries (message, traceback, or request_id).

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.

## Scope

### 1. TTL constant and purge

In `monitoring/error_log.py` add a module constant
`ERROR_RING_TTL_HOURS = 24` (that name and value). Do not add a
Settings field this slice.

Add `clear_expired()` on `ErrorLog`. Under the lock, drop entries
whose `ts` is missing, unparseable, or older than
`ERROR_RING_TTL_HOURS` compared to `datetime.now(timezone.utc)`.
Parse with `datetime.fromisoformat`. If the parsed value is
naive, treat it as UTC.

Call `clear_expired()` at the start of `record`, `recent`, and
`count` (inside the method, taking the lock once if you fold
purge into that critical section). After `recent` or `count`,
the deque must contain only non-expired entries. GET
`/api/v1/debug/errors` uses both `count` and `recent`; both
must purge or the JSON `count` lies.

`clear()` stays a full wipe. Do not change `MAX_ERRORS`.

### 2. Named tests

Add `tests/test_spec43_g10_retention.py`. No widgets. No live
Postgres. Use the process `error_log` or a private `ErrorLog()`;
if you use the global, clear in a fixture.

Exact names:

`test_error_ring_drops_expired_entries_on_recent`

`record` two entries. Set the first entry's `ts` to a UTC ISO
string more than 24 hours in the past. Leave the second fresh.
`recent()` must not include the expired `request_id`. `count()`
is 1. The expired `request_id` must not appear in
`json.dumps(error_log.recent())`.

`test_error_ring_drops_expired_entries_on_record`

`record` one entry; expire it via `ts`. `record` a second
fresh entry. After the second `record`, `count()` is 1 and only
the new `request_id` remains.

Also (any name): unparseable `ts` is dropped; `test_ring_buffer_capped_at_100`
stays green; IAM named tests stay green (do not edit those
files). Do not freeze wall-clock against a hardcoded calendar
date; set `ts` explicitly.

Do not assert on comments.

### 3. R17 sabotage

Exact edit: in `recent`, do not call `clear_expired` (return
the deque as today).

`test_error_ring_drops_expired_entries_on_recent` must fail
(expired `request_id` still present). Restore before the PR.
Do not sabotage by deleting the test. Do not sabotage IAM,
redaction, or the 100-cap.

If Databricks blocks in-place sabotage, an in-memory pytest
plugin that skips purge in `recent` only is the accepted
substitute. Named test must still fail; IAM tests must stay
green. Restore / drop the plugin before the PR.

## Out of scope

- Cloud Logging, GCS, regional buckets, access audit
- Scrubbing `debug_admin_token` in `redact_secrets`
- Changing IAM headers
- Armor, Play Integrity, LLM gateway
- Flutter, deploy, APK, hosted 0026

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

SHA, branch, pytest last line, files touched. Named tests in
the report must include
`test_error_ring_drops_expired_entries_on_recent` and
`test_error_ring_drops_expired_entries_on_record`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
