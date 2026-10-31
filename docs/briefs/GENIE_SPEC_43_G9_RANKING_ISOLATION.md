# Genie brief: SPEC-43 Gap 9 -- ranking isolation and per-place rate

Landed on `main` as `9b49fd0` (PR #101). Do not re-implement this slice.
Next: `docs/briefs/GENIE_SPEC_43_G5_SQLCIPHER_OPEN_FAILED.md`. Do not start
SQLCipher, Gap 7, Gap 10, Gap 11, deploy, or an APK without a new
brief.

## Goal

One user must not be able to flood ranking-corpus signals for one
venue, and those signals must not change SPEC-41 `pack_day` order.

Today `_interest_score` / `pack_day` never read the signal store.
Learned ranking is zero by omission, not by a gate. There is no
per-user per-place cap on `POST /api/v1/signals`. SPEC-43 Gap 9
remaining that this slice closes: one user or device cannot
materially move a venue score, and excess repeats are per-item
rejected.

This is SPEC-43 Gap 9 ranking isolation + rate only. Ownership
(`163a14c`) and closed schemas (`fb72545`) are on main. It is not
`derived_feature`, GPS plausibility, Gap 5, Gap 7, Gap 11, deploy,
or an APK. Do not turn learned ranking on.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (Gap 9)
- `docs/ENGINEERING_RULES.md` (R4, R14, R17)
- `models/signal_types.py`
- `routers/signal_router.py` (ingest loop)
- `services/database_service.py` (`record_signal`, `_signals`)
- `services/supabase_service.py` (`record_signal`)
- `services/catalog_itinerary.py` (`_interest_score`, `pack_day`)
- `tests/test_spec41_named_slots.py` (`_venue`, `_pack`)
- `tests/test_spec43_g9_signal_schema.py`
- `tests/test_signals.py`

Base branch: latest `main` (`4216ede`), including Gap 9 closed
schemas `fb72545` (PR #98).

Create and push:

`feat/spec43-g9-ranking-isolation`

Do not merge. Open one PR only after the gates below are green.

## Why this exists

Closed schemas stop junk keys. They do not stop 10,000 valid
`user_loved` rows on one `place_ref`, and they do not fail if someone
later adds those rows into `_interest_score`. This slice is the
ingest cap plus the R17-able isolation proof.

## Current production seams to reuse

- Ingest already rejects per item (type, schema, ownership, skew)
  then `record_signal`. Add the rate check after ownership/schema
  and **before** `record_signal`. Duplicate `signal_id` must still
  be a duplicate, not a rate reject: if `get_signal(signal_id)` is
  not None, skip the cap and let the existing idempotent path run.
- Count stored rows plus already-accepted items in the same batch
  for `(user_id, signal_type, place_ref)`.
- `pack_day` / `_interest_score` stay catalog-only. Do not read
  signals there except in the R17 sabotage (restore before PR).
- R4: a new count helper must exist on **both**
  `database_service` and `supabase_service`. No live Postgres.

Do not add CREATE TABLE. If you somehow add one, grant `service_role`
only. Do not create `derived_feature`.

## Scope

### 1. Rate cap

In `models/signal_types.py` (names yours):

- `RANKING_CORPUS_SIGNAL_TYPES`: frozenset of
  `user_loved`, `visited_confirmed`, `reroute_accepted`,
  `reroute_rejected`, `dish_loved`, `dish_ordered`
- `RANKING_CORPUS_PER_PLACE_CAP = 3`

Other client types (`session_start`, `node_skipped`,
`driver_card_shown`, ...) are not capped this slice.

Helper on both DB backends, e.g.
`count_signals_for_user_place(user_id, signal_type, place_ref) -> int`.
Supabase: query table `signal` filtered by `user_id`, `place_ref`,
and the type id (same as `record_signal`). In-memory: count
`_signals` values.

If type is in the corpus set and
stored_count + in_batch_accepted >= cap: per-item reject, reason
must contain `rate`, write nothing, do not derive.

### 2. Tests

New file `tests/test_spec43_g9_ranking_isolation.py`.

Named test that must exist with this exact name:

`test_one_user_cannot_materially_move_venue_score`

Build two same-category catalog venues with `_venue` from
`test_spec41_named_slots` (or a local copy of that helper). Use
`place_ref = venue_id`. Baseline `pack_day` venue_id sequence (same
args as `_pack`: target_count 4, GEO, `_DAY_START`, empty
`interest_ids` so scores tie and name/id order wins). POST as the
debug user `RANKING_CORPUS_PER_PLACE_CAP` `user_loved` rows for the
**trailing** venue. `pack_day` again with the same candidates.
Expect the venue_id sequence **identical** to baseline.

Also:

- Fourth distinct `user_loved` for the same `place_ref` is HTTP 200,
  that item in `rejected`, reason contains `rate`, `get_signal` is
  None. First three accept.
- A mixed batch of 4 new `user_loved` for one place: accepted==3,
  one rejected for `rate`.
- Retry of an already-stored `signal_id` is a duplicate, not a rate
  reject, even when the cap is already full.
- `session_start` is not capped (4 distinct ids still accept).
- `node_skipped` with `reason: too_tired` still accepts.

No Flutter. No live Postgres. Do not change `_interest_score` in the
landed diff.

### 3. R17 sabotage

Exact edit: in `_interest_score`, add a large bonus when
`db_service` has any `user_loved` whose `place_ref` equals the
venue `venue_id` (import the in-memory service the tests use).

`test_one_user_cannot_materially_move_venue_score` must fail.
Restore before the PR. Do not sabotage by deleting the test.

## Out of scope

- Creating `derived_feature`, method_version, sample_size columns
- GPS / time-plausibility, contributor quality, anomaly models
- Wiring signals into ranking or search
- Gap 5 SQLCipher, Gap 7 consent, Gap 10 logging, Gap 11
- Hosted 0026, Gap 1 Cloud Run, APK
- Flutter

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
