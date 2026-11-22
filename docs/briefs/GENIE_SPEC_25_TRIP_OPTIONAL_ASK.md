# Genie brief: SPEC-25 trip-optional Ask (slice 1, backend)

Read this whole file before touching anything. It is the complete job.
If something here conflicts with memory of an earlier brief, this file
wins. If something is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA. Base on that SHA, which is `origin/main` at or after
`406a45d` (docs PR #330).

Owning spec: `docs/specs/SPEC-25-ask-anything.md`, remainder "trip-optional
Ask" (design decisions 1, 2, 3, 4). Parents: SPEC-17 trust tiers and
envelope (interim five-tier set in `services/ask_service.py`), SPEC-43
outbound-DTO rule (no booking references, notes, times or coordinates
crossing the Ask boundary), SPEC-25 grounded trip-scoped Ask (`30a4270`,
Phase C `7d825c0`).

CI is the gate. Owner Windows `pytest` is allowed. No APK, no hosted
deploy, no Flutter change in this slice.

## 0. Why this exists

Every Ask today goes through `POST /api/v1/trip/event` and needs a
`trip_id`. A question standing in front of a restaurant before any trip
exists cannot be asked. Spec decision 1: one ask endpoint whose trip is
optional. Spec decision 3: a plan change with no trip is refused with a
reason, not improvised.

This slice adds the trip-optional endpoint and nothing else user-visible.
The Flutter entry point is slice 2 (not in this brief).

## 1. Bound

- Deterministic templates or refuse. No `llm.complete`, no model key
  read, no provider call. `handle_ask` is already deterministic this
  slice; keep it so.
- Region comes from the request. No GPS, no coarse-location permission,
  no new device capability.
- Read only. No trip write, no version bump, no quota charge against a
  trip, no server-side thread or message history (threads stay
  device-local per SPEC-25 Phase C).
- No new dependency. No migration. No new table.

## 2. Verified facts on `main` (re-verify in preflight; line numbers drift)

- `services/ask_service.py`:
  - `AskIntent` (closed set): `place_identity`, `opening_hours`,
    `dish_fact`, `trip_current_next`, `plan_change`, `today_tonight`,
    `nearby_option`, `practical_rule`, `compare`, `what_now`,
    `out_of_scope`.
  - `AskService.handle_ask(question, geo_region, user_id, is_anonymous,
    venue_name, venue_id, next_venue_name, current_node_summary,
    next_node_summary, llm_key_present, target_node_id, **kwargs)` takes
    `geo_region` directly. It does not need a trip object to answer
    place or rule questions.
  - Module-level `_shared_cache`, `_shared_budget`; breaker threshold 3.
  - `_emit_telemetry` never logs question text (keep that).
- Trip path: `routers/trip_router.py` `process_trip_event` (around line
  535) handles `EventType.ASK_INFO`, skips `save_trip`, returns
  `ask_response`. `agents/state_machine.py` around line 367 bypasses the
  semantic cache for ask_info.
- Identity: `resolve_identity` dependency (`security.py`) gives
  `identity.user_id` and `identity.identity_kind`.
- Preflight: find the registry of valid `geo_region` codes
  (`config/regions.py` `REGIONS`) and confirm the two December regions
  plus the Laos regions are in it.
- Preflight: find which intents read trip state. Expect
  `trip_current_next`, `today_tonight`, `what_now`, `plan_change`, and
  possibly `compare` or `nearby_option`. Record the list you find.

## 3. Trip-optional rules

Route: one new route, `POST /api/v1/ask`. Request body is a closed
object: `question` (string, 1 to 500 characters after trim), `geo_region`
(one of the registry codes), optional `trip_id`. No other keys; reject
extras with 422.

- With no `trip_id`, a question classified into a trip-only intent gets
  a refusal envelope with a reason and an offer to start a trip. It does
  not improvise trip facts. Trip-only intents (confirm in preflight):
  `trip_current_next`, `today_tonight`, `what_now`, `plan_change`.
- With no `trip_id`, `place_identity`, `opening_hours`, `dish_fact`,
  `practical_rule`, `nearby_option` and `compare` answer from the catalog
  for `geo_region` through the same `handle_ask` path, with the same trust
  tiers, the same source citation, and the same refusal on a retrieval
  miss.
- With a `trip_id`, the request is refused with 422 `use_trip_event`
  and points at the existing route. Do not add a second trip-scoped path.
  (The trip composer keeps `POST /trip/event` unchanged.)
- Trip ownership is not needed in the no-trip path because no trip is
  read. Anonymous identities are allowed, subject to the same budget and
  cache rules as the trip path.
- `geo_region` mismatch with a catalog row: refuse. A Laos region cannot
  return Dubai content (SPEC-25 acceptance). Add a test.
- Budget: the same `AskBudget` as the trip path. An exhausted budget
  returns `budget_exhausted` with no model call (there is none anyway)
  and no retrieval.
- Cache: the same `AskCache`. A repeated question in the same region hits
  cache with zero catalog reads where the cache allows.
- Telemetry: the same `AskTelemetry` fields. No question text, no
  identity, no coordinates.

## 4. Response

Reuse the existing `AskResponse` serialisation (the same JSON shape
`ask_response` uses on `TripEventResponse`). Add nothing to it. Add a
new Pydantic request model and a response model that wraps the same
`AskResponse` shape. Document the closed key set in the PR description.

SPEC-43 outbound rule: the response carries only the answer, tier,
source citation and refusal reason. It never carries booking
references, notes, times, node ids or coordinates.

## 5. Tests (must fail on main)

Backend (`tests/test_spec25_trip_optional_ask.py`), through
`POST /api/v1/ask` with the test client:

1. A place question for `zanzibar_tanzania` with no `trip_id` returns a
   grounded catalog answer with a source citation. Fails on main (route
   does not exist).
2. The same question for `laos_luang_prabang` returns no Zanzibar venue
   name. Fails on main.
3. A `plan_change` question with no `trip_id` returns a refusal with the
   start-a-trip offer and no change. Fails on main.
4. A `today_tonight` question with no `trip_id` returns a refusal, not a
   trip answer. Fails on main.
5. A question with `trip_id` returns 422 `use_trip_event`. Fails on main.
6. Missing or empty `question` returns 422. Extra key returns 422.
   `geo_region` outside the registry returns 422.
7. A retrieval miss returns the hedge or refuse tier, not an assert,
   and invokes no catalog write.
8. Repeated question: second call is a cache hit (`cache_status` hit).
9. Exhausted `AskBudget`: `budget_exhausted` path, no catalog read.
10. Telemetry records the intent and path, and the question text is absent
    from every captured log record (use `caplog`).
11. Response JSON has no key named `booking_reference`, `notes`,
    `scheduled_start`, `node_id`, `lat` or `lng` at any depth.
12. No model client is constructed (patch the LLM service to raise on
    any call; the test passes).
13. The trip route is unchanged: an existing trip ASK_INFO test passes
    without edits. Name it in the PR.

Existing tests: do not change expected values. Stop if more than three
existing tests need an edit.

R17: the PR branch is one backend commit (plus a test-only commit if
needed). Push also:

- `feat/spec25-trip-optional-ask-r17a`: from the tip, the trip-only
  refusal is removed so `plan_change` with no trip falls through to the
  trip path. Expected failures: 3, 4.
- `feat/spec25-trip-optional-ask-r17b`: from the tip, the `use_trip_event`
  check is removed so a trip id is accepted and ignored. Expected
  failures: 5.

The planning agent opens each as a draft PR, reads the failing test
names, closes them unmerged and deletes the branches.

## 6. Explicitly out

- Any LLM or model phrasing (`grounded_model_phrased` stays unreachable)
- Coarse location, GPS, or any new permission
- Server-side threads, message history, or suggested-question storage
- Catalog-backed place-detail prompts (separate remainder)
- Flutter entry point or repository change (slice 2)
- Changing the trip composer or `POST /trip/event`
- SPEC-17 claim registry or envelope changes
- Migrations, new tables, new dependencies, APK, hosted deploy

## 7. Stop rules

- Stop if the no-trip path needs a trip object to answer a catalog
  intent.
- Stop if any intent needs an LLM to answer.
- Stop if the response would need a field from the SPEC-43 excluded list.
- Stop if more than three existing tests need edits.
- Stop if the route cannot be added without changing `POST /trip/event`.

## 8. Gates

- ASCII only in added comments and strings (R14).
- No hard-coded test counts in docs (R16).
- `ruff check` and `ruff format --check` clean.
- Jobs: `pytest`, `lint`, `postgres-proof`, `docker-build`, `test`,
  `flutter`, `android-compile` green. `deploy` and `build` skipped.

## 9. PR

Branch `feat/spec25-trip-optional-ask` from the base SHA you were sent.
One backend commit, or two if the tests are separate. Do not merge. Push
the branch and the two `-r17a` / `-r17b` heads. Send the planning agent
the PR description (no `gh` on Genie compute); the planning agent opens
the PR.

The PR description must include: the preflight answers (trip-reading
intents list, region registry check), the closed request key set, the
response key set, a test-to-production table, R17 expected failures, any
existing test touched, and "no APK in this slice".

## Amendment 1 (planning agent, 2026-11-22, after Genie's preflight)

Preflight facts (base `568a729`):

- Trip-only intents are `today_tonight` (reads `trip_nodes`),
  `trip_current_next` (reads current and next node summaries) and
  `plan_change` (only meaningful with a trip). `what_now` is never produced by
  `classify_ask_intent` (it is reached only by `preferences.mode == "what_now"`
  on the trip route), so it cannot occur on the new route. `compare`,
  `nearby_option`, `practical_rule` and `dish_fact` do not read a trip. No intent
  needs an LLM.
- `REGIONS` has six codes: `dubai_uae`, `luang_prabang_laos`, `vang_vieng_laos`,
  `vientiane_laos`, `zanzibar_tanzania`, `nungwi_tanzania`. The earlier test 2
  code `laos_luang_prabang` was my error; use `luang_prabang_laos`.
- `retrieve_catalog_facts` finds a venue only from the `venue_name` argument,
  which the trip route fills from the current node. Place and hours questions
  therefore always miss with no trip.
- `AskBudget` is not enforced anywhere on main; budget and breaker activation
  stay deferred with the LLM slice.

Decisions:

1. Trip-only refusal (section 3, test 3 and 4) covers exactly `today_tonight`,
   `trip_current_next` and `plan_change`. Drop `what_now` from the list.
2. Venue name from the question (option A), in the new route only; do not
   change `handle_ask` or the trip route:
   - Find catalog venues in `geo_region` whose name, case-folded with whitespace
     collapsed, appears as a whole-word phrase in the case-folded question.
   - Ignore venue names shorter than 4 characters.
   - If several names match and one is contained in another, keep the longest.
   - Accept only when exactly one venue remains; pass its name (and id, if the
     catalog row has one) to `handle_ask` as `venue_name`. Zero or several
     remaining: pass no venue, so the answer is the normal retrieval-miss
     hedge or refusal. Never guess between venues.
   - No LLM, no network, no fuzzy matching, no edit distance.
3. Budget (option B): the new route does not enforce `AskBudget`, the same as the
   trip path. Replace section 3's budget bullet with: "No budget is enforced
   this slice (no model is called); activation is deferred with the LLM slice."
   Drop test 9.
4. Changed and added tests (`tests/test_spec25_trip_optional_ask.py`):
   - 1: a place question naming one Zanzibar catalog venue, region
     `zanzibar_tanzania`, no `trip_id`: grounded answer with a source citation.
   - 1b: a question naming two unrelated venues in the region: retrieval-miss
     hedge or refusal, no venue picked.
   - 1c: a place question naming no venue: retrieval-miss hedge or refusal.
   - 2: the same Zanzibar venue name asked with region `luang_prabang_laos`:
     no Zanzibar venue name or fact in the response. Region code is
     `luang_prabang_laos`.
   - 4b: a `trip_current_next` question with no `trip_id`: refusal with the
     start-a-trip offer.
   - 9 is dropped. Everything else in section 5 stands.
5. R17 additions:
   - `-r17a` (plan_change and today_tonight refusal removed): expected failures
     3, 4. Also remove the `trip_current_next` refusal in the same sabotage, so
     4b fails too: expected failures 3, 4, 4b.
   - `-r17b` unchanged: expected failure 5.
   - New `feat/spec25-trip-optional-ask-r17c`: from the tip, the venue matcher
     accepts the first match when several match. Expected failure: 1b.
6. Everything else in the brief stands, including the closed request key set
   (`question`, `geo_region`, optional `trip_id`; extras rejected).
