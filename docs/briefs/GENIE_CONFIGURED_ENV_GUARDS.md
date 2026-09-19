# Genie Brief: configured-env guards -- empty weather key and swap-no-LLM

Start a new branch from `origin/feat/spec10-booking-local-time` (`1cd7c6a`
or later). That branch has the destination-local booking wall-time fix.
Do not start from dirty local `feat/spec41-reachability`.

```text
feat/spec41-configured-env-guards
```

Do not merge. Do not deploy. Do not build an APK.
Do not touch `feat/spec25-grounded-ask`.
Do not implement named itinerary slots, `pack_day` booking reflow,
destination date-cap removal, place-detail cards, paste/parser work,
hotel lat/lng geocoding, or dual check-in/checkout UI.

Read first:

- `docs/AWAITING_VERIFICATION.md` (Sep 19 2026 laptop pytest and UI)
- `docs/ENGINEERING_RULES.md` (R17)
- `docs/WAYS_OF_WORKING.md`
- `services/weather_provider.py` (`WeatherProvider.__init__`)
- `agents/state_machine.py` (`_node_generate_response`)
- `tests/test_context_alerts.py`
  (`test_empty_string_api_key_is_unconfigured`,
  `test_no_openweather_key_returns_unconfigured_empty`)
- `tests/test_spec41_hours_eligibility.py`
  (`TestSwapStateMachine.test_swap_invokes_no_llm`)
- `tests/test_spec41_reachability.py`
  (`TestStateMachineSwap.test_no_maps_no_llm_on_swap`)

Do not edit this brief.

## Why this slice exists

Owner Windows laptop on `feat/spec10-booking-local-time` with a real
`.env` (OpenWeather + LiteLLM/Gemini keys):

- booking local-time tests: 11 passed
- flight/hotel + booking_anchors: 49 passed
- `pytest -q -ra`: 4 failed, 748 passed
- unsetting `$env:TB_OPENWEATHER_API_KEY` / `TB_LITELLM_API_KEY` /
  `TB_GEMINI_API_KEY` to `$null` still left all four red (settings already
  loaded from `.env`; empty-string constructor still falls through)

These are production predicates that only fail when keys exist. CI without
keys is not a substitute. Do not "fix" by skipping tests when keys are
present. Do not tell the owner to delete `.env`.

## Goal

After this slice, with OpenWeather and LLM keys loaded the same way the
laptop loads `.env`:

1. `WeatherProvider(api_key="")` is unconfigured. Explicit empty does not
   fall through to `settings.openweather_api_key`.
2. Alerts with that injected provider return `status == "unconfigured"`
   and `alerts == []`, even if settings still hold a real key.
3. `swap_activity` never calls `llm_service.generate_itinerary_response`
   or `generate_info_response`. Deterministic canned copy only, same as
   add/edit/delete booking and cancel.
4. The four named laptop failures pass. Full `pytest -q` is green.

## 1. WeatherProvider empty key

Current:

```text
self.api_key = api_key or settings.openweather_api_key
```

Empty string is falsy, so a real settings key wins. That makes
`is_configured` true and the alerts endpoint `available`.

Required:

- `api_key is None` means use settings.
- `api_key == ""` (or whitespace-only, if you strip) means unconfigured.
- A non-empty constructor argument is used as-is.

Do not change live OpenWeather fetch behavior for a real key.

R17: restore `api_key or settings.openweather_api_key`, run
`test_empty_string_api_key_is_unconfigured` with
`settings.openweather_api_key` patched to a non-empty dummy. It must go
red. Restore the fix. Name the test in the PR.

## 2. Swap never uses the LLM

`_node_generate_response` already returns canned text for cancel and
booking events, then:

```text
if settings.litellm_api_key or settings.gemini_api_key:
    ... await llm_service.generate_itinerary_response(...)
```

Swap is a structural event. SPEC-41: create and swap need no model when
deterministic inputs suffice. Laptop evidence: swap is `routing_tier=heavy`
and still calls `generate_itinerary_response` when a key exists; HTTP 200
with canned fallback after the mock cannot be awaited.

Required:

- `EventType.SWAP_ACTIVITY` returns a canned itinerary-updated (or
  no-candidates) string and returns before the configured-LLM branch.
- Do not patch tests to hide the call. Change production.
- Other HEAVY events that already depend on LLM copy are out of this
  slice. Do not broaden to Ask.

R17: temporarily restore swap falling through to the LLM gate; 
`test_swap_invokes_no_llm` must go red with a dummy
`settings.litellm_api_key`. Restore. Name the test in the PR.

Keep the existing maps/LLM spies in
`test_no_maps_no_llm_on_swap`. That test must also stay green with keys
loaded.

## Explicitly out

- Slot-shaped days, travel-day remaining slots.
- `pack_day` consuming bookings / silent reflow of conflicting activities.
- Hotel geocode / lat-lng on add_booking.
- Dual check-in and check-out on the hotel card.
- Catalog `max_days` UI removal.
- Flutter analyze infos (dangling docs, prefer_const). Do not churn 97 infos.
- SPEC-25, LangGraph, MCP, deploy, APK.

## Tests and gates

Must pass with keys present in the process environment (load `.env` or
patch settings to non-empty keys inside the four tests if the execution
host has no secrets; still prove the empty-string and swap predicates
against a non-empty settings key).

```text
pytest -q tests/test_context_alerts.py::test_empty_string_api_key_is_unconfigured
pytest -q tests/test_context_alerts.py::test_no_openweather_key_returns_unconfigured_empty
pytest -q tests/test_spec41_hours_eligibility.py::TestSwapStateMachine::test_swap_invokes_no_llm
pytest -q tests/test_spec41_reachability.py::TestStateMachineSwap::test_no_maps_no_llm_on_swap
pytest -q tests/test_spec10_booking_local_time.py
pytest -q
ruff check .
ruff format --check .
git diff --check
```

If you cannot load real secrets, add unit tests that patch
`settings.openweather_api_key` / `settings.litellm_api_key` to `'dummy'`
and still assert the four behaviors. The laptop already proved the
unpatched `.env` path.

## Done when

- Empty constructor key does not inherit settings.
- Swap does not call itinerary LLM helpers.
- Named R17 sabotages are documented.
- Booking local-time tests still pass (do not regress `1cd7c6a`).
- PR opened. No merge, no deploy, no APK.

## Commit style

ASCII in `.py` comments/docstrings (R14). LLM never mutates without HITL.
