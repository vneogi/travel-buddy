# Genie Brief: swap canned copy must not lie on no_candidates

Continue on `feat/spec41-configured-env-guards` from `1757daf`.
Do not start a new branch from main.

Do not merge. Do not deploy. Do not APK.
Do not reopen weather empty-key (that part of `1757daf` is accepted).
Do not implement slots, pack_day, hotel geocode, or Flutter infos.

Read:

- `agents/state_machine.py` (`_node_generate_response`)
- `docs/briefs/GENIE_CONFIGURED_ENV_GUARDS.md`

Do not edit this brief.

## Bug

`1757daf` returns early for every `SWAP_ACTIVITY` *before*
`no_candidates` and `breaker_tripped`:

```text
if SWAP_ACTIVITY:
    if venues_found: "Swapped to {venues[0].name}."
    else: "Activity swapped."
    return
if breaker_tripped: ...
if no_candidates: honest refusal
```

A refused swap (`no_candidates=True`, itinerary unchanged) now tells the
traveller the activity was swapped. If `venues_found` is still populated
from search, it can even name a venue that was not applied.

## Fix

Keep swap off the LLM path. Order must be:

1. cancel / booking canned returns (unchanged)
2. `breaker_tripped` fallback (unchanged)
3. `no_candidates` honest refusal (unchanged)
4. successful `SWAP_ACTIVITY` canned line, then return
5. configured LLM branch for remaining events

Name the applied venue only after a successful apply (itinerary actually
changed). Prefer the updated target node's `venue_name`, not
`venues_found[0]`.

## Tests

Add a TestClient swap that sets up a `replacement_venue_id` that is
unreachable or same as current so `no_candidates` is true. Assert:

- HTTP 200
- nodes unchanged
- `message` contains the existing no-candidate refusal, not "Swapped"
- `generate_itinerary_response` is not called (keys patched non-empty)

R17: move the swap canned return above `no_candidates` again; this new
test goes red. Restore.

```text
pytest -q tests/test_spec41_configured_env_guards.py
pytest -q tests/test_spec41_hours_eligibility.py::TestSwapStateMachine::test_swap_invokes_no_llm
pytest -q tests/test_spec41_reachability.py::TestStateMachineSwap::test_no_maps_no_llm_on_swap
pytest -q tests/test_spec10_booking_local_time.py
pytest -q
ruff check .
ruff format --check .
git diff --check
```

PR update on the same branch. Stop.
