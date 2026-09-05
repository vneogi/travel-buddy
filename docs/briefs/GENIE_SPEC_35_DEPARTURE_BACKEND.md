# Genie Brief: SPEC-35 Phase A Departure Backend

## Read first

- `docs/specs/SPEC-35-proactive-itinerary-notifications.md`
- `docs/specs/SPEC-29-context-alerts.md`
- `docs/specs/SPEC-27-app-lifecycle.md`
- `models/alerts.py`
- `services/weather_provider.py`
- `services/alert_evaluator.py`
- `routers/alerts_router.py`
- `services/google_maps_real.py`

## Scope

Implement only SPEC-35 Phase A: owner-scoped, in-app departure notification
candidates. Do not implement Flutter UI, OS push, device tokens, background
jobs, background location, dish recommendations, corpus mining, or the full
SPEC-17 claim store.

The endpoint must be useful with real provider data and honest when providers
or coordinates are absent.

## Required shape

Add:

- typed notification response models;
- an injectable route-provider interface and provider error type;
- a pure departure-candidate evaluator with injectable `now`;
- `GET /api/v1/trip/{trip_id}/notifications`;
- router registration;
- focused backend tests.

Use the configured Google Maps key through the route adapter if available.
Do not call the random mock `MapsService.get_transit_time` in a user-facing
path. Cache fresh route responses for at most five minutes using rounded
origin/destination coordinates, mode and departure-time bucket.

Reuse the existing `WeatherProvider` and its forecast blocks for the rain
policy buffer. Do not create a second weather client.

## Candidate rules

1. Load the trip and enforce ownership before provider calls.
2. Select only the next future pending, non-skipped node.
3. Destination is that node's coordinates.
4. Origin is the active or immediately preceding itinerary node with
   coordinates. Trip-region centre is never a departure origin.
5. If origin or destination is absent, return no departure candidate.
6. Request a departure-time-aware driving estimate and label the mode `by
   road` because transport mode is not yet reliably populated.
7. Use provider traffic duration once. Never apply an additional peak-hour
   multiplier.
8. Add the v1 ten-minute arrival policy buffer.
9. Add a separate ten-minute weather policy buffer only when fresh forecast
   evidence overlapping the departure/arrival window has rain probability at
   least 0.50.
10. Return the candidate only from ten minutes before its recommended
    departure until fifteen minutes after scheduled arrival.
11. Use `Leave by HH:MM` before the calculated departure and `Leave now` once
    it is due or overdue.
12. Use the deterministic ID defined by SPEC-35.

Provider failure is partial, not endpoint failure. Return `status: partial`
and no departure candidate if no fresh route result is available. Return 503
only for trip-storage failure.

## Do not

- Do not change `/trip/{trip_id}/alerts`.
- Do not persist location.
- Do not use trip-region centre as origin.
- Do not call an LLM or the state machine.
- Do not mutate nodes, consume quota, or emit structural events.
- Do not add `meal_preview` copy from bare `venue_dish.is_signature`.
- Do not claim `current traffic` when only normal duration is present.
- Do not add random variance or a synthetic peak-hour multiplier.
- Do not build push transport.

## Required proof cases

- non-owner is rejected before either provider is called;
- only next pending non-skipped node is evaluated;
- no credible origin or destination returns no candidate;
- traffic duration is used exactly once;
- rain adds ten policy minutes while preserving route duration evidence;
- stale/failed route data returns partial without failing unrelated response
  construction;
- before eligibility no candidate is returned;
- due/overdue copy says `Leave now`;
- repeated evaluation has the same ID;
- rescheduling changes ID and eligibility;
- evaluator has no LLM, mutation, event, or quota dependency;
- `/alerts` response remains backward compatible.

## Completion report

Return:

- branch name;
- head SHA;
- pull request URL;
- files changed;
- exact automated checks run and their results;
- any provider behavior that could not be exercised without credentials.

Do not merge the pull request.
