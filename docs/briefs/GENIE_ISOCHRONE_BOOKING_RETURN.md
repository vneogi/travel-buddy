# Genie brief: network reachability slice 2, booking return for What Now

Read this whole file before touching anything. It is the complete job.
If something here conflicts with your memory of an earlier brief, this
file wins. If something here is unclear, stop and ask; do not guess and
do not widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

## 0. Context

Decision record: `docs/decisions/NETWORK_REACHABILITY.md`. Slice 1
(`docs/briefs/GENIE_ISOCHRONE_PROVIDER.md`) is on main (PR #248,
`90b2fb5`): `services/reachability_provider.py`, `services/geo_polygon.py`,
and the What Now walking filter. Hosted Cloud Run has
`TB_REACHABILITY_PROVIDER=google_isochrones` ON since `00018-kjh`
(`docs/HOSTED_STATE.md`).

Because the main flag is already on in production, this slice MUST sit
behind a second flag that defaults to off. A deploy of this code must
not change hosted behaviour until the owner sets the new flag.

Slice 2 answers one question for What Now: "if I do this now, can I
still walk to my next booking in time?" Today that check is Haversine
only (`_violates_next_booking` -> `fits_next_lock`). Slice 2 adds one
reverse ("TO") walking isochrone around the next booking and drops
candidates outside it. Like slice 1 it is an intersection: it only
removes candidates Haversine keeps. It never adds one, never changes
`walk_min`, reason codes, sort keys, answer text, scheduling or packing.

### Why the rule is safe (read this, the tests depend on it)

Let `gap` = minutes from `now_utc` to the booking start, rounded UP to a
whole minute. Let `B` = the smallest band in `(15, 30, 45, 60, 90, 120)`
with `B >= gap`. Fetch the TO isochrone around the booking for `B`
minutes: the area from which the booking is reachable on foot within
`B` minutes.

For any candidate, the time left to walk to the booking after the
activity is `slack = gap - walk_to_candidate - dwell`, so
`slack <= gap <= B`. If the candidate is OUTSIDE the B-minute TO area,
walking from it to the booking takes more than `B` minutes, which is
more than `slack`. So the candidate provably misses the booking and can
be dropped. Inside the area proves nothing, so the candidate stays
(Haversine already decided it). This is why the band rounds UP, never
down.

### Verified API fact

Google Isochrones `travelDirection` accepts `FROM` and `TO`. `TO` is the
inbound (reverse) area: places from which you can travel to the origin
within `travelDuration`. WALK max is 7200 s. Same endpoint, same
headers, same field mask as slice 1.

## 1. Goal

1. Provider: a reverse walking isochrone, `walk_isochrone_to(...)`,
   sharing slice 1's cache (keyed separately by direction), spend
   circuit, error codes and logging rules.
2. A second flag, `TB_REACHABILITY_BOOKING_RETURN`, default `off`.
   Only the exact value `on` enables slice 2, and only when slice 1's
   provider is also available.
3. What Now: when enabled and applicable (section 5.4), fetch one TO
   isochrone around the next locked non-hotel booking and drop
   candidates outside it. Any failure falls back to today's behaviour.
4. Envelope field `what_now.booking_reachability_source`, closed set:
   `network_isochrone` | `haversine_estimate` | `not_applicable`.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm these exist on that SHA: `services/reachability_provider.py`
   (with `walk_isochrone`, `_cache_key`, `isochrone_spend_circuit`,
   `get_reachability_provider`, `_reset_for_tests`),
   `services/geo_polygon.py`, `tests/test_reachability_provider.py`,
   `tests/test_what_now_network_reachability.py`,
   `tests/test_spec46_what_now.py`. In `services/ask_service.py`:
   `fetch_what_now_reachability`, `handle_what_now(..., reach_polygons=)`,
   `_find_next_locked_non_hotel`, `_violates_next_booking`. In
   `models/schemas.py`: `WhatNowResult.reachability_source`. If any is
   missing or differs, stop.
3. Confirm `services/reachability_provider.py` has no `walk_isochrone_to`
   and `origin/feat/isochrone-booking-return` does not exist.
4. Branch: `feat/isochrone-booking-return`.

## 3. Read before editing

- `docs/decisions/NETWORK_REACHABILITY.md` (whole file)
- `docs/briefs/GENIE_ISOCHRONE_PROVIDER.md` (slice 1 rules; they all
  still apply)
- `docs/specs/SPEC-46-what-now-foreground-context.md` (closed reason
  codes, next-booking check)
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `services/reachability_provider.py` (whole file)
- `services/ask_service.py`: `fetch_what_now_reachability`,
  `handle_what_now`, `_find_next_locked_non_hotel`,
  `_violates_next_booking`
- `services/booking_constraints.py`: `fits_next_lock` (hotel skip,
  different region, different local day, flight cutoff)
- `agents/state_machine.py`: the What Now branch (the
  `fetch_what_now_reachability(` call)
- `models/schemas.py`: `WhatNowResult`
- `tests/test_what_now_network_reachability.py` (`StubProvider`,
  `_no_sockets`, fixtures to reuse)

## 4. Files you may touch

- `services/reachability_provider.py` (reverse direction only)
- `services/ask_service.py` (one new async helper, one new keyword-only
  parameter on `handle_what_now`, one envelope field)
- `agents/state_machine.py` (the What Now branch only)
- `models/schemas.py` (one field on `WhatNowResult`)
- `config/settings.py` (one field)
- `.env.example` (one line: `TB_REACHABILITY_BOOKING_RETURN=off`)
- `tests/test_booking_return_reachability.py` (new)

Nothing else. Do not edit existing tests, Flutter,
`services/booking_constraints.py`, `services/scheduler.py`,
`services/catalog_itinerary.py`, `services/transit.py`,
`scripts/isochrone_trial.py`, routers, migrations, `requirements*.txt`
or docs.

## 5. The change

### 5.1 Setting

`config/settings.py`, next to `reachability_provider`:

```
reachability_booking_return: str = "off"  # TB_REACHABILITY_BOOKING_RETURN: off | on
```

Any value other than exactly `on` means off.

### 5.2 Provider (`services/reachability_provider.py`)

- Add to the ABC:

  ```
  async def walk_isochrone_to(
      self, lat: float, lng: float, minutes: int, identity: object
  ) -> IsochroneResult: ...
  ```

  Make it a concrete method on the ABC that raises
  `ReachabilityError("not_configured")`, so existing test stubs that only
  implement `walk_isochrone` keep working unchanged.
- In `GoogleIsochronesProvider`, move the shared request path into one
  private method taking `direction` (`"FROM"` or `"TO"`).
  `walk_isochrone` calls it with `"FROM"` and must behave byte for byte
  as today: same body, same cache key, same log line. `walk_isochrone_to`
  calls it with `"TO"`.
- Body for TO is identical to FROM except `"travelDirection": "TO"`.
- Cache key: FROM keeps today's `f"{round(lat,3)},{round(lng,3)}:{minutes}"`.
  TO uses the same string plus `":to"`. Same TTL, same bound, one shared
  `OrderedDict`.
- `origin_outside` applies to TO too (the booking point must lie inside
  its own inbound area).
- Logging: FROM keeps `reachability provider=%s outcome=%s` exactly.
  TO logs `reachability provider=%s direction=to outcome=%s`. Closed
  code only; never the key, coordinates, URL or body.
- Spend: the same `isochrone_spend_circuit` and per-call estimate. No
  new circuit, no cap change.

### 5.3 Factory gate

Add:

```
def booking_return_enabled() -> bool:
```

True only when `settings.reachability_booking_return == "on"`. The
caller gets the provider from the existing `get_reachability_provider()`
(None when slice 1 is off or unkeyed). Slice 2 runs only when both are
true.

### 5.4 What Now wiring (`services/ask_service.py`)

Constants next to `_WALKING_CAPS`:

```
_BOOKING_RETURN_BANDS = (15, 30, 45, 60, 90, 120)
```

New async helper:

```
async def fetch_booking_return_reachability(
    trip_nodes: List[Dict[str, Any]],
    now_utc,
    geo_region: str,
    provider: Optional["ReachabilityProvider"],
    identity: object,
) -> Optional[tuple]:
```

Returns `(booking_node_id, band_minutes, polygons)` or `None`. It returns
`None` WITHOUT a provider call when any of these hold:

- `provider is None`;
- `_find_next_locked_non_hotel(trip_nodes, now_utc)` is `None`;
- that booking is a flight (`booking_type == "flight"`; flights use the
  150-minute cutoff, not walking);
- its `geo_region` is set and differs from `geo_region`;
- its destination-local date differs from `now_utc`'s destination-local
  date (use the same local-date helper `fits_next_lock` uses);
- its `lat`/`lng` are missing or not finite;
- `gap` (minutes, rounded up) is `< 1` or `> 120`.

Otherwise `band` = smallest value in `_BOOKING_RETURN_BANDS` that is
`>= gap`, then `await provider.walk_isochrone_to(lat, lng, band,
identity)`. On `ReachabilityError` or any other exception, return
`None`. What Now must never fail because of this.

Origin is the booking node's own `lat`/`lng` from `trip_nodes`. Never
read coordinates from preferences, headers or device fields.

`handle_what_now` gains one keyword-only parameter:
`booking_reach: Optional[tuple] = None`. It stays sync and
deterministic. Inside the candidate loop, in the existing
`if next_locked_booking is not None:` block, AFTER `_violates_next_booking`
returns False and BEFORE `has_next_booking = True`:

```
if booking_reach is not None and booking_reach[0] == next_locked_booking.get("node_id"):
    v_lat, v_lng = venue.get("lat"), venue.get("lng")
    if v_lat is not None and v_lng is not None:
        if not point_in_multipolygon(v_lng, v_lat, booking_reach[2]):
            continue
```

This applies for both `trip_position` and `region_anchor` contexts (the
rule in section 0 does not depend on the origin). A candidate without
coordinates is not dropped by this check.

Envelope, always present in `what_now_result`:

- `booking_reach is not None` -> `"network_isochrone"`
- `next_locked_booking` exists and the helper's applicability rules
  would hold (non-flight, same region, same local day, finite coords,
  `1 <= gap <= 120`) but `booking_reach is None` -> `"haversine_estimate"`
- otherwise -> `"not_applicable"`

Put the applicability test in one small pure function that both the
helper and `handle_what_now` call, so they cannot drift.

Do not add a reason code. `keeps_next_booking_reachable` keeps its
current meaning. Do not change the answer text. Do not change
`reachability_source`.

### 5.5 Schema

`models/schemas.py`, `WhatNowResult`:

```
booking_reachability_source: Literal[
    "network_isochrone", "haversine_estimate", "not_applicable"
] = "not_applicable"
```

Make sure it survives `TripEventResponse` the same way slice 1's
`reachability_source` does (slice 1 needed a follow-up fix for this;
see `test_trip_event_response_keeps_reachability_source`).

### 5.6 State machine (`agents/state_machine.py`)

In the What Now branch only. Get the provider once. If
`booking_return_enabled()` is true, run both fetches concurrently with
`asyncio.gather`, otherwise run only the slice 1 fetch exactly as
today. Pass `booking_reach=` into `handle_what_now`. Touch no other
branch.

## 6. Tests

`tests/test_booking_return_reachability.py`, exact names. No real
sockets: reuse the `_no_sockets` guard pattern and `httpx.MockTransport`.
Use a stub provider that records `walk_isochrone_to` calls.

Provider:

1. `test_to_request_body_differs_from_from_only_in_direction`
2. `test_from_request_and_cache_key_unchanged`
3. `test_to_and_from_cache_entries_are_separate`
4. `test_to_respects_spend_cap_before_http`
5. `test_to_logs_direction_and_never_key_or_coordinates` (caplog)
6. `test_abc_default_walk_isochrone_to_raises_not_configured`

Gate and helper:

7. `test_booking_return_off_by_default`
8. `test_booking_return_needs_exact_on_value`
9. `test_band_rounds_up_to_next_band` (gaps 1, 15, 16, 44, 46, 61, 91,
   120 -> 15, 15, 30, 45, 60, 90, 120, 120)
10. `test_no_call_when_gap_over_120_or_under_1`
11. `test_no_call_for_flight_hotel_other_region_or_other_day`
12. `test_no_call_when_booking_has_no_finite_coords`
13. `test_origin_is_booking_coords_not_preferences`
14. `test_provider_error_returns_none` (each `ReachabilityError` code
    and a bare `RuntimeError`)

What Now:

15. `test_no_booking_reach_candidates_identical_to_baseline`
16. `test_outside_to_area_drops_candidate_haversine_kept`
17. `test_inside_to_area_keeps_candidate`
18. `test_booking_reach_never_adds_candidate`
19. `test_booking_reach_for_other_node_id_is_ignored`
20. `test_candidate_without_coords_not_dropped`
21. `test_envelope_values_network_haversine_not_applicable`
22. `test_slice1_reachability_source_unchanged`
23. `test_trip_event_response_keeps_booking_reachability_source`

State machine:

24. `test_state_machine_booking_return_off_makes_no_to_call`
25. `test_state_machine_booking_return_on_passes_reach`
26. `test_touched_files_are_ascii`

All existing tests stay green unchanged, especially
`tests/test_reachability_provider.py`,
`tests/test_what_now_network_reachability.py` and
`tests/test_spec46_what_now.py`.

## 7. R17

Run each, confirm the named test fails, then restore:

A. Round the band DOWN instead of up: `test_band_rounds_up_to_next_band`
   fails.
B. Send `"FROM"` for the TO request:
   `test_to_request_body_differs_from_from_only_in_direction` fails.
C. Drop the `booking_return_enabled()` check in the state machine:
   `test_state_machine_booking_return_off_makes_no_to_call` fails.
D. Use preference coordinates as the origin:
   `test_origin_is_booking_coords_not_preferences` fails.

## 8. Stop rules

Stop and ask if:

- you need a file outside section 4, or an existing test must change;
- you need a new dependency;
- you want to apply this to create, corridor, swap, Add/Move or packing
  (out of scope; SPEC-41 packing stays Haversine);
- you want drive / two-wheeler modes, traffic-aware routing, or a map
  overlay;
- you want a new reason code, answer text or Flutter change;
- you want to change the spend caps or add a circuit.

## 9. Gates

```
ruff check . && ruff format --check .
pytest -q
git diff --check
```

All green. ASCII only in anything you add. Do not add `SPEC-NN`
references except to numbers with a file under `docs/specs/`.

## 10. Delivery

One commit on `feat/isochrone-booking-return`:
`feat: Isochrones booking-return check for What Now (flag off)`.
Push and verify the remote SHA. Do not open a PR. Do not merge. No `gh`.
No Cloud Run deploy and no env var change.

## 11. Report

1. Base SHA.
2. Branch and remote SHA.
3. `ruff` and `pytest -q` last lines.
4. `git diff --check` result.
5. Files touched, with +/- counts.
6. R17 A to D results.
7. Confirmation that slice 1 FROM behaviour (body, cache key, log line)
   is unchanged, and that no Flutter, packing, router or docs file
   changed.
8. Anything you were unsure about.

## 12. Owner steps (after merge; waits until the phone returns)

1. Deploy from `main` with the existing env vars preserved
   (`--update-env-vars`, never `--set-env-vars`). Slice 2 stays off.
2. Set `TB_REACHABILITY_BOOKING_RETURN=on` with `--update-env-vars`.
3. On a Zanzibar trip with a locked non-hotel booking later the same
   day (within two hours), run What Now. Cloud Run logs should show
   `reachability provider=google_isochrones direction=to outcome=ok`.
4. To turn it off, set the flag back to `off` with `--update-env-vars`.
