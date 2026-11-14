# Genie brief: SPEC-43 Gap 4 slice 18 -- nested export document builder

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

## 0. Context in one paragraph

Gap 4 export is on main: `execute_export` walks `EXPORT_STEPS`
parent-first and returns a flat list of `{table, method, via, rows}`;
`GET /api/v1/me/export` returns that list (minus `method` and `via`),
caller-only and rate-limited. SPEC-27 section 11 says export is "the same
data in a form a human can read", and SPEC-43 asks for a readable export
covering trips, parties, signals and events. Flat per-table rows do not
meet that: a traveller cannot see which nodes, parties or events belong
to which trip. This slice adds a pure function that turns the flat
result into one nested document grouped under trips. It is not wired to
the HTTP route yet (that is slice 19). No SQL, no route, no zip, no PDF.

## 1. Goal and the properties that matter

1. `build_export_document(results)` returns a nested document where
   every trip-scoped row sits under its trip, and party members sit
   under their party.
2. Row conservation: every input row appears in the output exactly
   once. Nothing is dropped and nothing is duplicated. Rows that cannot
   be attached to a trip in the export go into `unattached`, never into
   the bin.
3. Trip matching compares ids as text (`str(...)`), because
   `trip_party.trip_id` is text while `trip_states.trip_id` is a uuid.
4. The function is pure: the input is not mutated, and the output
   never aliases input rows (deep copies).
5. The function adds no identity data. It only regroups rows the
   caller's export already returned.

## 2. Preflight (do this first, stop if any check fails)

1. `git fetch origin`. Work from the `origin/main` SHA given in the
   message that sent you this brief. If `origin/main` has moved past
   it, say so and continue from the newer main only if it still
   contains every file in step 2; otherwise stop.
2. Confirm on that main these files exist: this brief,
   `services/data_rights_export.py`,
   `services/data_rights_export_memory.py`,
   `tests/test_spec43_g4_export_memory.py`,
   `routers/me_router.py`, `docs/ENGINEERING_RULES.md`.
3. Confirm `services/data_rights_export_document.py` does NOT exist,
   `tests/test_spec43_g4_export_document.py` does NOT exist, and
   `origin/feat/spec43-g4-export-document` does not exist. If any
   exist, stop and report.
4. Create a fresh branch from that main:
   `feat/spec43-g4-export-document`.

Never start work from an older SHA. Check the base before you write a
line.

## 3. Read before editing (read only; these are your patterns)

- `docs/ENGINEERING_RULES.md`: R14 (ASCII), R16 (no hard-coded pytest
  totals in docs; this slice writes no docs), R17 (a guard that cannot
  fail is not a guard).
- `services/data_rights_export.py`: `EXPORT_STEPS`, `EXPORT_REQUIRED`,
  `execute_export` and its result shape.
- `services/data_rights_export_memory.py`: `InMemoryExportBackend` and
  its join rules (`trip_id` compared as text).
- `tests/test_spec43_g4_export_memory.py`: the two-user `_seed_user`
  helper and the `seed_owner` test tag. Copy the helper into the new
  test file; do not import across test files.
- `routers/me_router.py`: read only, to see the current HTTP export
  shape. Do not edit it.

## 4. Files you may touch

- `services/data_rights_export_document.py` (new)
- `tests/test_spec43_g4_export_document.py` (new)

Nothing else. In particular do NOT change:

- `services/data_rights_export.py`, `services/data_rights_export_memory.py`,
  `services/data_rights_export_supabase.py`
- any `services/data_rights_erase*.py`, `services/data_rights_tombstone.py`,
  `services/data_rights_auth_delete.py`, `services/data_rights_token_deny.py`,
  `services/data_rights_cache_purge.py`
- `routers/me_router.py`, `monitoring/rate_limit.py`, `main.py`,
  `security.py`, `config/data_rights.py`, `tests/conftest.py`
- any existing test file
- any SQL or `supabase/migrations/**`
- `mobile/**`, requirements files, any doc, any brief

Do not write a new brief or any doc. Do not start slice 19.

## 5. The module: `services/data_rights_export_document.py`

ASCII only. Standard library plus `services.data_rights_export`. No SQL,
no network, no files, no logging, no print.

### 5.1 Input

`results` is a list of dicts, each with at least `table` (str) and
`rows` (list of dicts). It may be the direct return of
`execute_export` (which also carries `method` and `via`) or the HTTP
shape (only `table` and `rows`). Ignore any other keys.

Validate before building anything:

- Every table in `EXPORT_REQUIRED` appears exactly once.
- No table outside `EXPORT_REQUIRED` appears.
- `rows` is a list for each entry.

On any violation raise `ValueError` with a short message that does not
include row content or user ids.

### 5.2 Output shape (exact keys)

```
{
  "format": "travel-buddy-export",
  "version": 1,
  "account": {"user_tiers": [<rows>]},
  "trips": [
    {
      "trip": <trip_states row>,
      "nodes": [<trip_node rows for this trip>],
      "edges": [<trip_edge rows for this trip>],
      "parties": [
        {"party": <trip_party row>, "members": [<party_member rows>]}
      ],
      "commands": [<trip_command rows for this trip>],
      "signals": [<signal rows for this trip>],
      "events": [<event_log rows for this trip>]
    }
  ],
  "unattached": {
    "trip_node": [...], "trip_edge": [...], "trip_party": [...],
    "party_member": [...], "trip_command": [...],
    "signal": [...], "event_log": [...]
  }
}
```

Every key above is always present, even when its list is empty.

### 5.3 Attachment rules

- Trips: one entry per `trip_states` row, in input order. Trip key is
  `str(row["trip_id"])`. If two `trip_states` rows share a trip key,
  raise `ValueError` (the export is inconsistent; do not guess).
- `trip_node`, `trip_edge`, `trip_command`, `signal`, `event_log`:
  attach to the trip whose key equals `str(row.get("trip_id"))`. A
  missing or `None` `trip_id`, or one that matches no exported trip,
  goes to `unattached[<table>]`.
- `trip_party`: attach under the matching trip's `parties` as
  `{"party": row, "members": []}`; otherwise `unattached["trip_party"]`.
- `party_member`: attach to the `members` list of the party whose
  `str(party_id)` matches, but only if that party was attached to a
  trip. Members of an unattached party, or of no exported party, go to
  `unattached["party_member"]`. Duplicate `party_id` across
  `trip_party` rows: raise `ValueError`.
- Order within every list follows input order.
- Every row in the output is a deep copy (`copy.deepcopy`).

### 5.4 Helper

Also expose `count_rows(document) -> Dict[str, int]` that counts rows
per source table in a built document (walking `account`, `trips` and
`unattached`). Tests use it to prove conservation against the input.
It must count from the document, not from the input.

Module docstring: nested, human-readable grouping of a caller's export;
pure; not wired to HTTP yet; zip/PDF/pagination/route wiring are
remainders.

## 6. Tests: `tests/test_spec43_g4_export_document.py`

No network. No `supabase` package. Copy `_seed_user` from
`tests/test_spec43_g4_export_memory.py` (users A and B, `seed_owner`
tag). Use `InMemoryExportBackend` plus `execute_export` for realistic
input; build small hand-written inputs for edge cases.

Exact test names (each must exist; add more only if they add proof):

1. `test_document_conserves_every_exported_row`
   Seed A and B, `execute_export(A)`, build the document.
   `count_rows(doc)` equals the per-table row counts of the input
   (derived from the input, no hard-coded numbers). Also check that
   the multiset of rows (as sorted reprs) per table is equal between
   input and document.

2. `test_trip_children_nest_under_their_trip`
   Using the same document: for every trip entry, every row in
   `nodes`, `edges`, `commands`, `signals`, `events` has
   `str(trip_id) == str(trip["trip_id"])`. With the seed helper,
   `unattached` is empty for every table.

3. `test_party_members_nest_under_their_party`
   Every member under a party has the same `str(party_id)` as that
   party, and every party sits under the trip whose id matches its
   text `trip_id`.

4. `test_text_and_uuid_trip_ids_match`
   Hand-built input: a `trip_states` row with a `uuid.UUID` trip_id and
   a `trip_party` row with the same id as a string. The party nests
   under the trip (not in `unattached`).

5. `test_orphan_rows_go_to_unattached_not_dropped`
   Hand-built input with: a `signal` with `trip_id` None, an
   `event_log` whose trip_id matches no trip, a `trip_node` for an
   unknown trip, a `party_member` whose party is not exported. Each
   lands in the right `unattached` list, and `count_rows` still equals
   the input counts.

6. `test_document_contains_only_the_callers_rows`
   From the two-user seed, the document built from `execute_export(A)`
   contains no row with `seed_owner == B`, and its JSON dump
   (`json.dumps(doc, default=str)`) does not contain B's user id.

7. `test_input_is_not_mutated_and_output_does_not_alias`
   Deep-copy the input before building; after building, the input
   equals the copy. Mutating a row inside the document does not change
   the input.

8. `test_rejects_missing_unknown_or_duplicate_tables`
   Missing `signal` entry -> ValueError. Extra `cached_responses`
   entry -> ValueError. `trip_node` listed twice -> ValueError. The
   error messages contain no user id.

9. `test_rejects_duplicate_trip_or_party_keys`
   Two `trip_states` rows with the same trip_id -> ValueError. Two
   `trip_party` rows with the same party_id -> ValueError.

10. `test_empty_export_has_every_key`
    Every required table present with empty rows. Output has `format`,
    `version == 1`, `account.user_tiers == []`, `trips == []`, and
    every `unattached` key present and empty.

11. `test_accepts_http_shape_without_method_and_via`
    Strip `method` and `via` from an `execute_export` result. The
    document equals the one built from the full result.

12. `test_export_document_module_is_ascii`
    Read `services/data_rights_export_document.py` and assert
    `.isascii()`, and that it contains no `import logging` and no
    `print(`.

## 7. R17 sabotage (required, and must be reported)

Two sabotage runs, each restored before the next. No repo file may
keep the sabotage.

A. In the builder, drop rows that would go to `unattached` (do not
   append them). Under that sabotage
   `test_orphan_rows_go_to_unattached_not_dropped` must fail.
   `test_document_conserves_every_exported_row` may stay green (the
   seed has no orphans); say so in the report.

B. In the builder, compare trip ids without `str()` (raw equality).
   Under that sabotage `test_text_and_uuid_trip_ids_match` must fail.

If in-place editing is blocked, an in-memory pytest plugin that patches
the builder is the accepted substitute; drop every plugin before the
PR. Confirm the module file hash is identical before A and after the
last restore.

## 8. Stop rules

Stop and report instead of improvising if:

- any preflight check in section 2 fails;
- an existing test fails for a reason related to this change;
- an existing test fails for any other reason not named in section 9;
- you feel you need to edit a file outside section 4;
- you are about to wire the document into `GET /api/v1/me/export`,
  add a query parameter, a zip, a PDF, Content-Disposition, or
  pagination;
- you are about to add SQL, a migration, or touch 0026;
- you are about to write a brief, a doc, or a second slice.

Never "fix" an unrelated failure, never skip or xfail a test, never
loosen an assertion, never force-push over another branch.

## 9. Gates

Run from the repo root, with `backend/.venv` if it exists. Use
`ruff==0.16.3` (CI pin). A newer ruff is not the gate.

```
ruff check .
ruff format --check .
python3 -m pytest tests/ -q --tb=short
git diff --check
```

Known pre-existing failures. These are not yours; do not touch them:

- `test_sparse_create_with_limited_hours_succeeds` (hard-coded date;
  failed CI on PR #211, #214 and #217)
- `test_today_tonight_includes_venue_name` (fails near ICT midnight)

Anything else failing is yours until proven otherwise. Confirm touched
files are ASCII only. If `ruff format --check .` fails on a file you
are not allowed to edit, stop and report; do not reformat it.

Dart / Flutter checks are not part of this slice. Do not run them.

## 10. Out of scope (record as remainders, do not build)

- Wiring the document into `GET /api/v1/me/export` (slice 19)
- Zip, PDF, Content-Disposition download, pagination
- Durable tombstone table: blocked for now because a new migration
  table must also be classified in the 0026 RLS test, and hosted SQL
  waits on the `rolbypassrls` confirmation
- Erase-route tombstone hook, retention jobs
- Flutter leave / local wipe, Armor, Play Integrity, deploy, APK
- Frontend findings F1-F4 in `UX_BACKLOG.md`

## 11. Delivery

1. Commit on `feat/spec43-g4-export-document` with the message:
   `SPEC-43 Gap 4 slice 18: nested export document builder`.
2. Push that branch. Verify the pushed SHA from the remote
   (`git ls-remote origin feat/spec43-g4-export-document`), not from
   your local clone.
3. Do not merge, do not deploy, do not open or edit any other branch.
   This compute has no `gh`; the reviewer opens the PR from your
   branch. Do not try to work around that.

## 12. Report (exactly these fields, in this order)

1. Base `origin/main` SHA you started from.
2. Branch name and pushed SHA (verified from the remote).
3. `pytest` last line, and the name of every failing test.
4. `ruff check`, `ruff format --check`, `git diff --check` results
   (name the ruff version).
5. Files touched (must be only those in section 4).
6. For the two-user seed: per-table input counts and `count_rows`
   output counts for A (they must be equal), and the number of trips
   in the document.
7. Confirmation that orphan rows landed in `unattached` (test 5) and
   that text/uuid trip ids matched (test 4).
8. Confirmation the document contains no B rows and no B user id.
9. The R17 tests that failed under sabotage A and B, by name, and
   confirmation the sabotage was removed and the module hash matches
   the pre-sabotage hash.
10. Anything you were unsure about, or anything you chose not to do.

Do not edit this brief, `PROJECT_STATUS`, or `HANDOFF`.
