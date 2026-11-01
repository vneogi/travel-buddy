# Genie brief: SPEC-43 Gap 9 -- derived facts keep method version and sample size

This is the open Gap 9 derived-fact first slice. Implement it. Do not
start a `derived_feature` table, hosted 0026, Flutter, deploy, or an
APK.

## Goal

Server-derived facts must carry `method_version`, `sample_size`, and
provenance so a later aggregator can refuse n=1 poisoning. Today
`derive_arrival_delta` writes `value_json.method = server_derived` and
`source_signal_id`, but it does not pass `provenance=` into
`record_signal`, so the row defaults to `client_emit`. There is no
`method_version` and no `sample_size`.

This is SPEC-43 Gap 9 derived-fact metadata only. Ownership, schemas,
ranking isolation, trip-place, and GPS are on main. It is not a new
table, not wiring derived facts into `pack_day`, not Flutter, deploy,
or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 9
  acceptance: derived facts retain method version, sample size, and
  provenance)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `services/arrival_delta_service.py` (`record_signal` call)
- `services/observed_duration_service.py` (out of this slice except
  do not break it)
- `services/database_service.py` (`record_signal` provenance default)
- `services/supabase_service.py` (`record_signal` provenance column)
- `routers/signal_router.py` (`_compute_provenance` is client-only)
- `tests/test_arrival_delta.py`
- `tests/test_spec43_g9_signal_ownership.py`

Base branch: latest `main` (`e8621a4`), including Gap 9 GPS
`08253cb` (PR #122).

Create and push:

`feat/spec43-g9-derived`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 9 acceptance: derived facts retain method version, sample size,
and provenance. A later ranking reader that treats `arrival_delta` as
client_emit cannot apply a minimum-sample gate. Stamp the fields on
the existing derived signal now. Do not invent a second fact table
this slice (hosted 0026 is still unapplied; no CREATE TABLE).

## Current production seams to reuse

- Keep writing `arrival_delta` through existing `record_signal`.
  Same deterministic `signal_id`. Same `value_numeric` minutes.
- Pass `provenance=` explicitly. Do not rely on the
  `client_emit` default.
- `value_json` already has `method` and `source_signal_id`. Keep
  those. Add `method_version` and `sample_size` there too so a
  `get_signal` reader sees them without a second column.
- `sample_size` for one `visited_confirmed` is `1`.
- `method_version` is a named constant `ARRIVAL_DELTA_METHOD_VERSION = 1`.
- Ownership re-check in `derive_arrival_delta` stays.
- Do not change `pack_day` or `_interest_score`.
- Do not change `derive_observed_duration` this slice (edge column
  has no provenance JSON).
- Do not add a signal type. Do not add a migration.

No CREATE TABLE. No new pip dependency. No Flutter. No live
Postgres. Do not apply 0026.

R4: `record_signal` already exists on both backends with
`provenance`. Do not add a new DB method.

## Scope

### 1. Stamp

In `derive_arrival_delta`, when it calls `record_signal`:

`provenance` dict (required keys):

- `method`: `server_derived`
- `method_version`: `ARRIVAL_DELTA_METHOD_VERSION` (1)
- `sample_size`: 1
- `source_signal_id`: the visited_confirmed id

`value_json` dict (required keys, keep existing):

- `method`: `server_derived`
- `source_signal_id`: same
- `scheduled_start`: keep as today
- `method_version`: 1
- `sample_size`: 1

Do not log lat/lng or other GPS.

### 2. Named tests

Add `tests/test_spec43_g9_derived.py`.

In-memory `db_service` only. Reuse trip-create / visited_confirmed
ingest from `tests/test_spec43_g9_trip_place.py` or
`tests/test_arrival_delta.py` so a real `arrival_delta` row exists.

Named tests that must exist with these exact names:

`test_derived_arrival_delta_retains_method_version_and_sample_size`

POST a trip-linked `visited_confirmed` that produces an
`arrival_delta` (analytics consent is autouse-granted unless
`real_consent`). Find the derived row (`signal_type ==
arrival_delta`). Assert:

- `provenance["method"] == "server_derived"`
- `provenance["method_version"] == 1`
- `provenance["sample_size"] == 1`
- `provenance["source_signal_id"]` equals the client signal_id
- `value_json["method_version"] == 1`
- `value_json["sample_size"] == 1`
- `provenance["method"] != "client_emit"`

`test_derived_arrival_delta_is_not_client_emit`

Same setup. `provenance["method"]` is `server_derived`. The
visited_confirmed row (if stored with provenance) may still be
`client_emit`.

Also add (any name):

- Existing arrival_delta numeric tests still pass (do not weaken
  `tests/test_arrival_delta.py`)
- Foreign trip still writes no derived row (existing ownership
  tests stay green)
- `pack_day` / `_interest_score` files are not in the diff

Do not assert on comments.

### 3. R17 sabotage

Exact edit: omit `method_version` from the `provenance` dict passed
to `record_signal` (leave `value_json` as the landed stamp).

`test_derived_arrival_delta_retains_method_version_and_sample_size`
must fail. Restore before the PR. Do not sabotage by deleting the
test. Do not sabotage sample_size.

## Out of scope

- CREATE TABLE `derived_feature`
- Wiring derived facts or loves into `pack_day` / search
- `derive_observed_duration` provenance
- Minimum-sample gate inside ranking (no ranking reader yet)
- Flutter, Gap 11 remainders, Gap 7 ledger, Gap 8 HMAC, Gap 10 IAM
- Hosted 0026, deploy, APK, `pm clear`

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

## Report

SHA, branch, pytest last line, files touched. Named tests in the
report must include
`test_derived_arrival_delta_retains_method_version_and_sample_size`
and `test_derived_arrival_delta_is_not_client_emit`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.