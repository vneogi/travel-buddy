# Genie brief: SPEC-43 Gap 3 -- strip booking fields from the heavy LLM payload

This is the open job. Roles, hard stops, and R17 ritual are in
`docs/briefs/GENIE_SPEC_43_G10_IAM_A.md` (Who you are, Who else
is, How a slice moves, Hard stops). Do not re-read all of
SPEC-43. Do not enable personal-trip LLM. Do not start the
provider-region matrix, embedding canaries, Armor, Play
Integrity, SQL cache, `derived_feature`, hosted 0026, Flutter,
deploy, or an APK.

## Goal

`LLMService.generate_itinerary_response` JSON-dumps
`trip_state["nodes"][:5]` into the user message sent to
`complete` -> `litellm.acompletion`. A node can carry
`confirmation_code`, `booking_notes`, `lat`, and `lng`.
`venues_found` also includes `lat`/`lng`. Heavy path is the
leak. Create/swap stay deterministic and do not need this
payload to apply a change.

This is SPEC-43 Gap 3 outbound itinerary DTO only. It is not
turning LLM on, not killing HEAVY_FALLBACK, not embeddings.

Read before editing:

- `docs/specs/SPEC-43-security-privacy-and-data-governance.md`
  (Gap 3 only: never send booking reference, notes, exact
  coordinates, user ID)
- `docs/ENGINEERING_RULES.md` (R14, R17)
- `services/llm_service.py` (`generate_itinerary_response`,
  `complete`, `generate_info_response`)
- `agents/state_machine.py` (`_node_generate_response` heavy
  branch -- read, do not change unless the dump lives there)
- `models/schemas.py` (`TripNode`)
- `monitoring/redact.py` (`redact_secrets` -- reuse, do not
  rewrite)

Base branch: latest `main` (`228e6b4`), including Gap 10 ring
TTL `12588c2` (PR #153).

Create and push: `feat/spec43-g3-itinerary-dto`

Do not merge. Open one PR after the gates are green.

## Why this exists

Gap 3 acceptance: canary booking codes, notes, and coordinates
never appear in completion payloads. `model_dump` of the trip
is not an allowlist. LiteLLM never sees fields we did not name.

Do not build a second orchestrator. Strip (or rebuild) the
dict that goes into `json.dumps` before `complete`.

## Current production seams to reuse

- Keep spend circuit, fallback `except Exception` (do not
  swallow `SpendCapped`), synthetic embeddings, deterministic
  Ask/swap/create.
- Keep `user_id` as the spend identity argument to `complete`.
  Do not put `user_id` inside the prompt text.
- Reuse `redact_secrets` on the serialized user-context string
  after the allowlist dump (keys in notes would still be
  caught).
- Do not log the prompt, `user_context`, or LiteLLM kwargs.

No CREATE TABLE. No Flutter. No live Postgres. Do not apply 0026.
Do not set `TB_LITELLM_API_KEY` in tests.

## Scope

### 1. Allowlisted node DTO

Add a helper (in `llm_service.py` or `services/llm_public.py`)
`public_itinerary_nodes(nodes: list) -> list`.

Each output dict may contain **only** these keys, when present
on the input dict: `venue_name`, `scheduled_start`,
`duration_minutes`, `is_locked`, `status`, `node_kind`,
`slot_name`, `geo_region`, `vibe_tags`, `micro_location`.

Drop everything else, including `confirmation_code`,
`booking_notes`, `lat`, `lng`, `node_id`, `venue_id`,
`import_source`, `names_local`, `place_source`. Input that is
not a dict is skipped.

`generate_itinerary_response` must dump
`public_itinerary_nodes(trip_state.get("nodes", [])[:5])`, not
the raw nodes.

For `venues_found[:3]`, dump dicts that keep `name`,
`micro_location`, `vibe_tags` only. Drop `lat` and `lng`.

Pass the JSON strings through `redact_secrets` before building
`messages`.

Do not change `generate_info_response` this slice (no trip
dump there). Do not change HEAVY_FALLBACK.

### 2. Named tests

Add `tests/test_spec43_g3_itinerary_dto.py`. No widgets. No
live Postgres. No real LiteLLM network.

Exact names:

`test_itinerary_llm_payload_omits_booking_canary`

Build a `trip_state` dict whose first node includes:

- `confirmation_code`: `G3-CANARY-PNR-9f3a` (exact)
- `booking_notes`: `Window seat for G3-CANARY-NOTE`
- `lat`: `19.876543`
- `lng`: `102.134567`
- ordinary `venue_name`: `Wat Xieng Thong`

Monkeypatch `LLMService.complete` (or `litellm.acompletion`) to
capture `messages` and return a tiny fake content dict. Call
`generate_itinerary_response` with that trip, a user_message
that does **not** contain the canaries (`Swap the afternoon
stop.`), and `venues_found` that includes the same lat/lng.

`json.dumps(captured messages)` must not contain
`G3-CANARY-PNR-9f3a`, `G3-CANARY-NOTE`, `19.876543`, or
`102.134567`. It must contain `Wat Xieng Thong`.

`test_public_itinerary_nodes_drops_restricted_keys`

Pass a node dict with both allowed keys and
`confirmation_code` / `lat`. Result dicts have no restricted
keys. Do not treat this helper-only test as the Gap 3 canary;
the named canary above must go through `generate_itinerary_response`.

Also (any name): `user_id` is passed to `complete` as the
argument, not interpolated into `messages`. Do not assert on
comments.

### 3. R17 sabotage

Exact edit: in `generate_itinerary_response`, dump
`trip_state.get("nodes", [])[:5]` again (skip the helper).

`test_itinerary_llm_payload_omits_booking_canary` must fail
(canary PNR present in captured messages). Restore before the
PR. Do not sabotage spend, IAM, or ring TTL.

If Databricks blocks in-place sabotage, an in-memory pytest
plugin that restores the raw dump in
`generate_itinerary_response` only is the accepted substitute.
Named canary must still fail. Drop the plugin before the PR.

## Out of scope

- Enabling LLM for personal trips
- HEAVY_FALLBACK / provider-region matrix
- Embedding Ask-text canaries
- `generate_info_response` question redaction
- Armor, Play Integrity, Flutter, deploy, APK, 0026

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
`test_itinerary_llm_payload_omits_booking_canary`.
Do not merge. Do not edit this brief, PROJECT_STATUS, or HANDOFF.
