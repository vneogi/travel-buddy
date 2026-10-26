# Genie brief: SPEC-43 Gap 9 -- trip-linked signal ownership

Landed on `main` as `163a14c` (PR #81). Do not re-implement this slice.
Gap 12 navigation privacy landed through `f486079`. Next:
`docs/briefs/GENIE_SPEC_43_G9_SIGNAL_SCHEMA.md`.

## Goal

A caller must not attach signals or derived facts to someone else's trip.

Today `POST /api/v1/signals` stamps `user_id` from the JWT, then uses a
client-supplied `trip_id` to load party context, `trip_day`, and to run
`derive_arrival_delta` / `derive_observed_duration`. Ownership is not
checked. User B can name user A's `trip_id` and still get a stored row
plus derived writers touching that trip.

This is SPEC-43 Gap 9 ownership only. It is not closed value_json schemas
for every type, ranking influence gates, quarantine, Gap 2 (already on
main), Gap 5, Gap 11, deploy, or an APK.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 9)
- `routers/signal_router.py`
- `services/arrival_delta_service.py`
- `services/observed_duration_service.py`
- `tests/test_signals.py`
- `tests/test_party.py`
- `docs/ENGINEERING_RULES.md`
- `docs/WAYS_OF_WORKING.md`

Base branch: latest `main`, including Gap 2 `0b8125f` (PR #80).

Create and push:

`feat/spec43-g9-signal-ownership`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Gap 2 closed PostgREST. The live write path is still FastAPI plus
service_role. Ingest is the remaining hole: a Bearer for B plus A's
`trip_id` poisons A's party-stamped signals and derived duration/arrival
facts.

## Scope

### 1. Ownership gate on ingest

When `trip_id` is present (non-empty), require that trip to exist and
`trip_states.user_id` (or the in-memory equivalent) to equal the
authenticated `user_id`. Do this *before* `_build_party_context`,
`record_signal`, `trip_day`, and any derive call.

If the check fails: per-item reject (same shape as unknown
`signal_type`). Stable reason containing `trip` and `owner` or
`ownership`. Do not write the signal. Do not stamp party_context. Do
not call derive services.

If `trip_id` is omitted or null: keep current behaviour (session_start
and other trip-optional types still ingest).

If `trip_id` is present, owned, but the trip has no party: still accept
the signal and omit party_context (SPEC-03 missing-party rule). Missing
party is not missing ownership.

Unknown / other-user `trip_id` is now a reject. Update
`test_signal_unknown_trip_still_succeeds` (or delete it) so it expects
rejected + no stored row. Do not keep a test that proves the hole.

Use one helper (name yours) so ingest and derived writers share it.
Do not copy a second ownership rule that can drift.

### 2. Derived writers

`derive_arrival_delta` and `derive_observed_duration` must re-check
ownership inside the function when `trip_id` is set, even if ingest
already checked. If not owned: return without writing derived rows.

Do not add new tables. Do not change signal_id idempotency.

### 3. Tests

`tests/test_spec43_g9_signal_ownership.py`.

Use two debug users (`X-Debug-User-Id`). Create a trip as A. POST a
trip-linked `user_loved` (and one `visited_confirmed`) as B with A's
`trip_id`.

Must include named test:

`test_foreign_trip_id_is_rejected_and_writes_nothing`

That test fails unless: HTTP 200 with that item in `rejected`,
`accepted=0` for it, no signal row, no party_context write, no
arrival_delta / observed_duration row for A's trip.

Also:

- A posting to A's trip still accepts
- omitted `trip_id` still accepts
- existing signal type / captured_at / idempotency tests stay green
  (update only the unknown-trip case)

No Flutter. No new pytest for live Postgres.

### 4. R17 sabotage

1. Temporarily skip the ingest ownership check (leave derive checks
   or skip both -- ingest skip is the one that must make the named
   test fail).
2. Run `test_foreign_trip_id_is_rejected_and_writes_nothing`.
3. Confirm that exact test fails.
4. Restore.
5. Re-run the focused file green.

Report the test name that failed.

## Non-goals

- closed schemas / size limits: `docs/briefs/GENIE_SPEC_43_G9_SIGNAL_SCHEMA.md`
- ranking influence, sample-size, quarantine
- Gap 2 hosted apply / two-JWT PostgREST
- Gap 5, Gap 11
- switching FastAPI off service_role
- Flutter, deploy, APK, postgres-proof apt

## Gates

```bash
ruff check .
ruff format --check .
pytest -q -ra --strict-markers
pytest -q tests/test_spec43_g9_signal_ownership.py tests/test_signals.py tests/test_party.py tests/test_arrival_delta.py tests/test_observed_duration.py
git diff --check
```

No Flutter.

If you add a CREATE TABLE (you should not), grant `service_role` only.
