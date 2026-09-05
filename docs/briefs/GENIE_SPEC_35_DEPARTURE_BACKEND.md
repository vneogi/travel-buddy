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
- `services/catalog_itinerary.py`
- `routers/trip_router.py`
- `config/regions.py`

## Scope

Implement only SPEC-35 Phase A: owner-scoped, in-app departure notification
candidates. Do not implement Flutter UI, OS push, device tokens, background
jobs, background location, dish recommendations, corpus mining, or the full
SPEC-17 claim store.

The endpoint must be useful with real provider data and honest when providers
or coordinates are absent.

## Mandatory schedule-time gate

Do this before evaluating departure reminders:

1. Add optional `TripState.schedule_basis`.
2. Fix catalog trip creation so the requested date is combined with 09:00 in
   `REGIONS[geo_region].timezone` using `zoneinfo.ZoneInfo`, then converted to
   a timezone-aware UTC instant for storage.
3. Set `schedule_basis` to `region_local_v1` on trips created through that
   corrected path.
4. Do not set or infer the marker for existing trips.
5. Suppress departure candidates when the marker is absent/unknown or the
   destination node's region has no registered IANA timezone.
6. Calculate in UTC, but format `Leave by HH:MM` in the destination region's
   timezone. Return the UTC `recommended_departure_at` and the IANA
   `time_zone` together.

Do not rewrite legacy trip times. Do not use the server or device timezone as
the destination timezone.

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
2. Enforce the `region_local_v1` schedule gate before provider calls.
3. Select only the next future pending, non-skipped node.
4. Destination is that node's coordinates.
5. Origin is the active or immediately preceding itinerary node with
   coordinates. Trip-region centre is never a departure origin.
6. If origin or destination is absent, return no departure candidate.
7. Request a departure-time-aware driving estimate and label the mode `by
   road` because transport mode is not yet reliably populated.
8. Use provider traffic duration once. Never apply an additional peak-hour
   multiplier.
9. Add the v1 ten-minute arrival policy buffer.
10. Add a separate ten-minute weather policy buffer only when fresh forecast
   evidence overlapping the departure/arrival window has rain probability at
   least 0.50.
11. Return the candidate only from ten minutes before its recommended
    departure until fifteen minutes after scheduled arrival.
12. Use `Leave by HH:MM` before the calculated departure and `Leave now` once
    it is due or overdue.
13. Use the deterministic ID defined by SPEC-35.

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
- Do not send reminders for legacy trips with unknown wall-clock semantics.
- Do not format departure copy in server-local time.

## Required proof cases

- non-owner is rejected before either provider is called;
- Laos catalog creation stores 09:00 Asia/Vientiane as the corresponding UTC
  instant and marks `region_local_v1`;
- Dubai catalog creation does the same using Asia/Dubai;
- legacy trips without the marker return no departure candidate and make no
  provider call;
- changing the process timezone does not change eligibility or formatted
  destination-local copy;
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
