# Genie Brief: SPEC-40 Fix 1 — Backend proofs only

Continue `feat/spec40-guided-create` at current HEAD (`355cc7c` or later).
Do not start Flutter work. Do not merge. Do not deploy.

Read first: `docs/specs/SPEC-40-guided-create-trip.md`, `docs/ENGINEERING_RULES.md`.
Do not edit this brief.

## Goal

Make the Python proofs actually fail if the implementation regresses.

## Required changes (Python only)

1. Replace `test_legacy_create_no_end_date_returns_same_sequence`.
   Compare omitted-`end_date` POST output to `nodes_from_catalog(...)` on the
   same seeded rows: same venue names, venue IDs, and count (`TARGET_STOPS`).
   Add sabotage that would fail if that comparison were two identical POSTs.

2. `interest_ids: null` must return typed 422 `invalid_interests`.
   Update `CreatePreferences` and replace `test_null_interest_ids_accepted_as_empty`.
   Keep empty list `[]` as balanced/allowed.

3. Scope `RequestValidationError` remapping in `main.py` to:
   - path `POST /api/v1/trip/create`;
   - loc starting with `("body", "preferences", "interest_ids")`.
   Add a test that `/trip/event` validation errors stay the generic detail list.

4. Options proof: `set(max_days_by_region) == set(supported_regions)` and
   POST with each advertised interest ID succeeds.

5. Patch and `assert_not_called` `hybrid_venue_search` and the reroute
   consume/quota method. Assert `daily_reroute_count` is unchanged.

6. Corridor `end_date` test must use a **valid three-segment** Laos corridor
   plus top-level `end_date`. A one-segment body does not prove this guard.

Do not reopen builder/dedup unless a new test fails it.

## Gates

```text
pytest -q -ra
ruff check . --config pyproject.toml
ruff format --check .
```

Report pass/fail/skip. Push the SHA. Stop. Do not start Fix 2.
