# Genie brief: SPEC-58 slice 1a, import backend (name match and batch import)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. This brief replaces the earlier `GENIE_SPEC58_PASTE_PLAN_IMPORT.md`
(renamed to this file and rewritten after your preflight stop on
2026-11-24). Your stop was correct; the earlier brief's "(Flutter)" PR
title and its ambiguous lookup stop rule were my slips. This slice is
BACKEND ONLY and a new endpoint and command are expected.

If something is unclear, stop and ask; do not guess and do not widen
scope. Start only when the planning agent (or owner) sends this brief
with a real base SHA.

Owning spec: `docs/specs/SPEC-58-paste-your-plan-import.md`. Read it
first, especially sections 2 (owner decisions 4 to 6), 3, 6 and 9.

## 0. Scope in one paragraph

Two server pieces, and nothing on the phone. (1) A small name-match
endpoint: stop names plus region in, a deterministic catalog match out,
with no embedding, no model call and no reroute quota. (2) A batch
`import_plan` command that adds many confirmed stops to a trip in one
command, reusing the existing catalog `direct_add` and trip-private
`uncatalogued_add` checks per item, consuming one reroute in total.

## 1. Gate and tooling

- Backend only. No Flutter change, no APK, no hosted deploy.
- No schema change, no migration, no new dependency. If you need one,
  stop (section 7).
- Gate is CI (`pytest`, `lint`, `postgres-proof`, `docker-build`).
- Rules: R14 (ASCII only in new files), R16 (no hard-coded test counts
  in docs). Never print tokens or credentials.

## 2. Preflight (do first; report before coding)

Report the answer to each in your first message. If an answer hits a
stop rule in section 7, stop there.

1. **Normaliser and aliases.** `services/uncatalogued_add_service.py`
   has `normalize_name`. Find what alias or local-name data a catalog
   venue has (for example `names_local`, taxonomy aliases). State exactly
   which fields the match may read. Do not read anything that is not
   already on the venue row.
2. **Region validation.** How a request names a region today and how a
   trip resolves its region or corridor segment per date
   (`direct_add_service.day_context`). The match endpoint takes a
   registered region id only.
3. **Where each add check lives.** Name the functions the batch command
   will call for a catalog item and for a plain item. Confirm they can
   be called per item without sending an HTTP request or a second
   reroute charge. If they cannot be reused as is, say what a minimal
   refactor looks like; do not copy their logic.
4. **Time to slot.** `services/day_slots.slot_from_time` maps a datetime
   to a slot. Confirm it can be used to choose a slot from a pasted
   local time for a given region.
5. **Per-item results.** The batch needs per-item accepted or refused
   results, but `process_event` returns `updated_trip_state`. Propose
   where the results go without a breaking change (for example an added
   optional field). If this needs a breaking change, stop.
6. **Empty-day trip creation.** Confirm a trip can be created with all
   days empty (SPEC-42 flexible span) through an existing create path.
   Say which path. If it needs a schema change or new endpoint, stop.
7. **Existing tests** that assert the reroute count for adds, or that
   enumerate `add_activity` modes; list them. They must pass unchanged.

## 3. Build

### 3.1 Name-match endpoint

- Authenticated route under the existing trip router (name it in your
  preflight reply, for example `POST /api/v1/trip/catalog_match`).
- Request: `{ "geo_region": "<registered region id>", "names": ["..."] }`.
  1 to 60 names, each trimmed, 2 to 80 characters. Refuse a bad region,
  an empty list, an over-limit list or a bad name with 422 before any
  lookup.
- Response, per name in request order:
  `{ "name": "<as sent>", "match": { venue_id, name, geo_region,
  provenance } | null, "near": [ up to 3 of the same shape ] }`.
- Rules, in order: exact normalised name, then exact normalised alias
  (only the fields you named in preflight 1), set `match`. Otherwise
  `near` is up to three venues whose normalised names share every token
  of the sent name or the reverse, sorted by name then venue id. Otherwise
  both empty.
- Deterministic. Zero `generate_embedding`, zero `llm.complete`, zero
  `hybrid_venue_search`. Read-only: no write of any kind.
- No reroute quota is used and no event is created. Use the existing
  per-user rate limiting pattern if one applies to read endpoints.
- Privacy: do not log names or the request body. Log only counts.

### 3.2 Batch import command

- Keep `EventType.ADD_ACTIVITY`. Add a fourth typed mode `import_plan`
  beside `direct_add`, `ask_to_add` and `uncatalogued_add`. Do not
  change those three.
- `preferences`:

```json
{
  "mode": "import_plan",
  "items": [
    {"kind": "catalog", "venue_id": "...", "target_date": "2026-12-27",
     "target_slot": "morning_tour"},
    {"kind": "plain", "name": "Sunset jetty", "target_date": "2026-12-27",
     "target_slot": "dinner", "typical_dwell_minutes": 60}
  ]
}
```

- 1 to 60 items. Any other `kind`, a missing field, or an over-limit
  list is refused 422 before persist (`invalid_mode`, `invalid_items`).
  For `plain`, the dwell is required and traveller-stated (15 to 240);
  never default it.
- Processing: sort items by date then `SLOT_ORDER`, then request order.
  For each item call the existing check and insert code from preflight
  3 (catalog direct-add for `catalog`, uncatalogued add for `plain`).
  Later items see the nodes earlier items added in the same batch
  (occupancy, previous-walk, `fits_next_lock`).
- A refused item does not stop the batch. It is recorded with its
  existing refusal `code` and traveller copy. Accepted items land.
- Result: if at least one item is accepted, persist once: version +1,
  exactly one reroute consumed. If every item is refused, persist
  nothing, consume nothing, and return 422
  `import_plan_refused` with the per-item results.
- Per-item results go where preflight 5 agreed. Each result:
  `{index, status: "added"|"refused", node_id|null, code|null,
  message|null}`.
- Reuse; do not copy. Do not write `venues_rag`, `venue_dish`,
  `venue_external_id` or taxonomy tables. Plain nodes have null
  `venue_id` and `place_source=trip_private`. Zero `llm.complete`, zero
  `hybrid_venue_search`.
- Replays and concurrent writes use the existing `commit_trip_command`
  path, so they cannot consume a second reroute.

## 4. Tests

New files `tests/test_spec58_catalog_match.py` and
`tests/test_spec58_import_plan.py`. Test names should describe the
behaviour. Cover at least:

Name match:
1. exact normalised name returns `match`; case, accents and extra
   spaces do not matter;
2. a local-name alias returns `match` (only if preflight 1 allows it);
3. token-subset names return `near` in a stable order, `match` null;
4. unknown name returns both empty;
5. patched `generate_embedding`, `llm.complete` and
   `hybrid_venue_search` are never called (assert call counts);
6. no reroute quota used and no event written;
7. bad region, empty list, 61 names and a 1-character name are refused
   before any lookup;
8. no request name appears in captured logs.

Batch import:
9. three catalog items and one plain item across two empty days all
   land: one version bump, exactly one reroute consumed;
10. a refused item (for example slot already filled by an earlier item
    in the batch) is reported with its code while the others land;
11. every item refused: nothing persisted, no quota used, 422
    `import_plan_refused` with per-item results;
12. plain item has null `venue_id`, `place_source=trip_private`, the
    posted dwell, and no hours; no catalog table is written;
13. a plain item whose normalised name collides with a catalog venue is
    refused `catalog_match`;
14. over-limit (61) and a plain item with no dwell are refused before
    persist;
15. `direct_add`, `ask_to_add` and `uncatalogued_add` single-item
    behaviour is unchanged (existing tests pass without edits).

Do not edit existing tests. If one must change to pass, stop.

## 5. Pull request

- Branch: `feat/spec58a-import-backend` from current `origin/main`.
- Title: `feat(spec58a): catalog name match and batch plan import (backend)`.
- Body: preflight answers 1 to 7, a test-to-production table, the exact
  list of existing tests touched (should be none), and a line saying
  there is no Flutter, schema, dependency or deploy change.
- Also push three R17 sabotage branches, one commit each from the
  feature head, and state the expected failing tests:
  - `-r17a`: the name match calls `generate_embedding` (expect test 5).
  - `-r17b`: the batch consumes one reroute per accepted item (expect
    test 9).
  - `-r17c`: a plain item is written to a catalog table or given a fake
    `venue_id` (expect test 12).
  Branch names: `feat/spec58a-import-backend-r17a`, `-r17b`, `-r17c`.
- Do not merge anything and do not open PRs; the planning agent opens
  them and reads CI. If a sabotage does not fail only its named tests,
  say so.

## 6. Non-goals

Any Flutter change; any model or embedding call; any new table or
column; changing the three existing add modes; more than one stop per
named slot; whole-day excursion items; outcome signals; party context;
long-tail places.

## 7. Stop rules (write a question, do not widen scope)

Stop and report, quoting the preflight line, if:

- the match needs an embedding, a model call, or more than names and
  region;
- the batch cannot reuse the existing add checks without copying or
  weakening them;
- per-item results need a breaking change to the `process_event` contract;
- empty-day trip creation needs a schema change or a new endpoint;
- any test can only pass by changing a SPEC-41, SPEC-42 or SPEC-10 check,
  or by editing an existing test;
- you need a new dependency or migration.

## 8. Report format

End your report with: PR-ready branch and head SHA; preflight answers 1
to 7; the test-to-production table; the three R17 branch heads and their
expected failing tests; any stop rule hit.
