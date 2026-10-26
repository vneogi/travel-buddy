# Genie brief: SPEC-43 Gap 9 -- closed signal value_json schemas

Landed on `main` as `fb72545` (PR #98). Do not re-implement this slice.
Next: `docs/briefs/GENIE_SPEC_43_G5_BACKUP.md`. Do not start
Gap 5, Gap 7, Gap 10, Gap 11, deploy, or an APK without a new brief.

## Goal

Client `value_json` must be a closed map: known keys only, bounded
size. Unknown fields, spoofed `party_context`, and oversized JSON
must be per-item rejected and must not be stored.

Today `models/signal_types.py` `PAYLOAD_SHAPES` is documentation.
Ingest copies `sig.value_json` then merges server `party_context`.
`test_party.py` proves extra keys such as `original_field` are
stored. SPEC-43 Gap 9 remaining: unknown fields, excessive values,
and oversized JSON are rejected with typed errors.

This is SPEC-43 Gap 9 closed schemas only. Ownership (`163a14c`) is
already on main. It is not ranking influence, quarantine, Gap 5,
Gap 7 consent, Gap 11, deploy, or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 9)
- `models/signal_types.py` (`PAYLOAD_SHAPES`, `NODE_SKIPPED_REASONS`)
- `routers/signal_router.py` (ingest loop, party_context merge)
- `mobile/lib/services/signal_service.dart` (current client keys;
  include `dish_name` for dish types)
- `tests/test_signals.py`
- `tests/test_signal_types.py`
- `tests/test_party.py`
- `tests/test_spec43_g9_signal_ownership.py`
- `docs/ENGINEERING_RULES.md` (R1, R14, R17)
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including Gap 12 trip-route ownership
`f486079` (PR #95) and docs `2aaff3e` (PR #96).

Create and push:

`feat/spec43-g9-signal-schema`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Ownership stops user B from naming user A's trip. It does not stop a
client from stuffing arbitrary JSON onto an owned trip. That is the
poisoning hole this slice closes at ingest, not the ranking-influence
hole.

## Current production seams to reuse

- Unknown `signal_type`, server-derived types, `node_skipped` reason
  enum, dish `entity_type`/`entity_id`, captured_at skew, and trip
  ownership already reject per-item. Add schema reject in the same
  loop, **before** party_context merge and `record_signal`.
- Server still stamps `party_context` (and session_start `trip_day`)
  after a valid client map. Those keys are not client-allowlisted.
- Client sending `party_context` is spoofing. Reject it.
- Do not change ownership helper, derive re-check, or Flutter emit
  shapes except if a test currently sends a key the allowlist must
  include (see `dish_name`).

Do not add CREATE TABLE. If you somehow add one, grant `service_role`
only.

## Scope

### 1. Allowlist

One map in `models/signal_types.py` (name yours) from each
**client-emittable** type to a frozenset of allowed `value_json`
keys. Align with `PAYLOAD_SHAPES` **and** current
`SignalService` payloads:

- `user_loved`, `visited_confirmed`: empty set (or no object)
- `reroute_accepted`: `replacement_ref`
- `reroute_rejected`: `rejected_refs`
- `node_skipped`: `reason`
- `dish_loved`, `dish_ordered`: `dish_name`
- `prompt_dismissed`: `kind`, `attribute`, `entity_id`
- `driver_card_shown`: `place_ref`, `was_offline`, `name_source`
- `name_confirmed`: `place_ref`, `lang`, `shown_value`, `verdict`
- `booking_added`: `booking_type`, `import_source`
- `session_start`: `cold_start`, `minutes_since_last_open`,
  `trip_day`, `trip_id`

`value_json` null or `{}` is allowed. Extra keys are not. Nested
objects other than these maps are not required this slice.

Max UTF-8 size of `json.dumps` of the **client** `value_json` before
merge: 4096 bytes. Oversize is a per-item reject.

Reject reason must contain `schema` or `unknown` (unknown key) or
`size` (oversize). Do not write the row.

`node_skipped` invalid reason stays as today (enum reject can stay
ahead of the allowlist).

### 2. Tests

New file `tests/test_spec43_g9_signal_schema.py`.

Named test that must exist with this exact name:

`test_unknown_value_json_field_is_rejected`

POST as the debug user a `user_loved` with
`value_json: {"original_field": "x"}` (and otherwise valid
fields). Expect HTTP 200, that item in `rejected`, `accepted=0` for
it, and `get_signal` is None.

Also:

- `user_loved` with no `value_json` still accepts
- client `party_context` in `value_json` is rejected
- oversize `value_json` is rejected
- `node_skipped` with `reason: too_tired` still accepts
- owned-trip `user_loved` still accepts; stored `party_context` may
  still be server-stamped

Update `test_party.py` / ownership tests that send `original_field`
so they no longer require storing unknown keys. Do not keep a test
that proves extra keys are stored.

No Flutter. No live Postgres.

### 3. R17 sabotage

Exact edit: skip the unknown-key reject (comment out or always
return ok from the schema helper) so `original_field` is stored.

`test_unknown_value_json_field_is_rejected` must fail. Restore
before the PR. Do not sabotage by deleting the test.

## Out of scope

- Ranking influence, sample-size, quarantine, contributor quality
- Gap 5 SQLCipher, Gap 7 consent, Gap 10 logging, Gap 11
- Hosted 0026, Gap 1 Cloud Run, APK
- Changing Flutter `SignalService` key names unless a production
  emit would be rejected (then add the key to the allowlist, do not
  break emit)

## Gates

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

If `backend/.venv` exists, use that interpreter. No Flutter.

## Report

SHA, branch, pytest last line, files touched. Do not merge. Do not
edit this brief, PROJECT_STATUS, or HANDOFF.
