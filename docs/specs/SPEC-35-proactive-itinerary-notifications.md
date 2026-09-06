# SPEC-35: Proactive Itinerary Notifications

> Status: PHASE A BACKEND DONE (PR #50, `ccfa41e`) AND PHASE A2 CLIENT DONE
> (PR #52, `1379da8`). OS push remains SPEC-27. Meal previews remain
> suppressed.
>
> Extends SPEC-29 context alerts. Depends on SPEC-13 for region timezones,
> SPEC-16 for stable itinerary nodes and edges, SPEC-17 for factual provenance, SPEC-19 for licensed
> review-derived dish claims, SPEC-22 for the shared interruption budget, and
> SPEC-27 if an in-app candidate is later delivered as an OS push.
>
> No migration number is claimed. Numbers are assigned at implementation time.

## Goal

Give a traveller a useful reason to keep the itinerary current and reopen the
app during the trip:

1. tell them when to leave for the next stop using provider-backed traffic and
   weather conditions; and
2. shortly before a meal, surface one evidence-backed dish worth considering.

The first product slice is an in-app notification feed evaluated on itinerary
load, foreground and resume. The backend and Flutter banner are live. They do
not request background location and do not send OS push notifications.

## Product copy contract

Examples describe the intended tone, not strings for an LLM to improvise:

- `Leave for Kuang Si Falls by 08:20. The drive is about 42 minutes with
  current traffic; 10 extra minutes were added for forecast rain.`
- `Lunch at Tamarind is coming up. Khao soi is listed as a signature dish in
  our guide.`
- After licensed corroboration exists: `Lunch at Tamarind is coming up.
  Licensed travel sources repeatedly mention the khao soi.`

The backend must not say `most popular`, `reviewers recommend`, `current
traffic`, or `rain expected` unless the corresponding typed evidence is
present and fresh.

## Scope of the backend slice

Add a read-only endpoint:

    GET /api/v1/trip/{trip_id}/notifications

It returns actionable notification candidates for the authenticated trip
owner. It never mutates the itinerary, consumes reroute quota, calls an LLM,
or marks a candidate delivered. The existing SPEC-29
`GET /api/v1/trip/{trip_id}/alerts` endpoint remains compatible.

The client renders those candidates in-app. OS push transport, device tokens,
and closed-app delivery remain owned by SPEC-27.

## Schedule-time correctness gate

A departure reminder is unsafe if the itinerary's wall-clock meaning is
ambiguous. The current catalog creator converts `start_date` to UTC and then
sets the hour to 09:00. For Laos that represents 16:00 local time, while the
current itinerary UI may still show the components as 09:00. Building a
reminder directly on that value would make server action time and displayed
itinerary time disagree.

Phase A therefore includes a narrow time-basis correction:

- catalog creation constructs 09:00 in `REGIONS[geo_region].timezone` and then
  stores the resulting timezone-aware UTC instant;
- `TripState` carries `schedule_basis: "region_local_v1"` only after every
  generated node has been interpreted this way;
- a node's `geo_region` must resolve to an IANA timezone in the region registry;
- calculations and provider requests use UTC instants;
- notification copy formats `HH:MM` in the destination node's region timezone;
- the response carries both `recommended_departure_at` as an ISO UTC instant
  and `time_zone` as the IANA zone used for display.

Legacy trips with a missing/unknown `schedule_basis` receive no departure
candidate. Do not silently reinterpret or rewrite their stored times. They may
be recreated or migrated by a separately reviewed operation. This fail-closed
rule is preferable to a precisely calculated reminder for the wrong hour.

## Notification types

### 1. `departure_reminder`

The evaluator considers only the next pending, non-skipped itinerary node.
The destination must have coordinates. The origin is selected in this order:

1. an active or immediately preceding itinerary node with coordinates;
2. an explicit foreground location supplied by a future location-aware
   request, with consent; or
3. no candidate.

Trip-region centre coordinates are not a valid origin for a departure
reminder. They are sufficient for regional weather in SPEC-29 but would create
a misleading departure time.

For the first slice, road travel is explicit. If `trip_edge.transport_mode` is
absent, the provider may request a driving estimate, but copy must say `by
road`; it must not imply walking, rail, or a booked transfer. Once a transport
mode is stored, the provider request and copy use that mode.

The route provider is asked for a departure-time-aware duration. When it
returns both normal and traffic duration, use the traffic duration exactly
once. Do not apply an additional hard-coded peak-hour multiplier.

    recommended_departure_at =
        destination.scheduled_start
        - route_duration_minutes
        - arrival_buffer_minutes
        - weather_buffer_minutes

Policy buffers are separate from provider observations:

- `arrival_buffer_minutes`: 10 in v1;
- `weather_buffer_minutes`: 10 when fresh forecast evidence for the route
  window has rain probability at least 0.50, otherwise 0.

The response labels both values as policy buffers. Rain is not silently folded
into the claimed provider route duration.

The candidate becomes eligible ten minutes before
`recommended_departure_at`. Before that it is not returned. Once the time is
reached, copy says `Leave by HH:MM`; if that time is already past, it says
`Leave now`. It expires fifteen minutes after the destination's scheduled
start.

If the route provider is unavailable, the backend does not invent traffic. A
fresh cached provider result may be used. With neither live nor cached route
evidence, omit the departure candidate while still returning any other
available candidates.

### 2. `meal_preview`

A node qualifies when its resolved venue category is a meal venue
(`restaurant`, `cafe`, or a future category declared in data) and it starts
within the next 60 minutes. The candidate expires fifteen minutes after the
scheduled start.

Dish selection is deterministic and has no LLM in the request path:

1. prefer a displayable SPEC-17 claim for `popular_dish` supported by at least
   two independent, licensed sources;
2. otherwise use a curated `venue_dish.is_signature` row only when it has
   stored editorial provenance, with copy that calls it a `signature dish in
   our guide`;
3. otherwise emit no meal preview.

`is_signature` alone does not prove popularity, and the existing bare rows do
not qualify until provenance is stored. It must never produce `popular`, `most
ordered`, `reviewers love`, or equivalent copy.

Google and TripAdvisor review scraping is out of scope. SPEC-19 permits
review-derived claims only from openly licensed corpora, with corpus,
reference, cited span, observation time, licence and independence retained.
One source may produce `ask`, not a factual meal notification. Two copied
sources are still one source after content deduplication.

The selected dish carries the SPEC-17 envelope. A missing source, tier, or
`as_of` value suppresses the meal candidate rather than falling back to bare
text.

## Response shape

    {
      "trip_id": "trip-123",
      "refreshed_at": "2026-10-04T01:05:00Z",
      "status": "available",
      "notifications": [
        {
          "notification_id": "...",
          "type": "departure_reminder",
          "priority": "trip_critical",
          "node_id": "node-7",
          "title": "Time to head to Kuang Si Falls",
          "message": "...",
          "eligible_at": "...",
          "expires_at": "...",
          "recommended_departure_at": "2026-10-04T01:20:00Z",
          "time_zone": "Asia/Vientiane",
          "deep_link": "/trip/trip-123/node/node-7",
          "evidence": {
            "route": {
              "source": "configured_route_provider",
              "observed_at": "...",
              "normal_duration_minutes": 34,
              "traffic_duration_minutes": 42,
              "mode": "driving",
              "origin_basis": "previous_node"
            },
            "weather": {
              "source": "openweather",
              "observed_at": "...",
              "rain_probability": 0.63
            },
            "policy": {
              "arrival_buffer_minutes": 10,
              "weather_buffer_minutes": 10
            }
          }
        }
      ]
    }

`meal_preview.evidence.dish` uses the SPEC-17 envelope and also carries the
licensed corpus references when the claim is review-derived.

`status` is `available`, `partial`, or `unconfigured`. Provider failure is
isolated per notification type: a traffic outage must not turn a valid meal
preview into a 503 response. The whole endpoint returns 503 only when trip
storage itself is unavailable.

## Identity, deduplication and suppression

`notification_id` is a deterministic hash of:

    trip_id, notification_type, node_id, scheduled_start, evaluator_version

Repeated foreground refreshes return the same ID. A reschedule creates a new
ID because its action time changed.

The backend applies the SPEC-22 interruption decision before returning
interruptive candidates. Priority order in this slice is:

1. departure reminder that is due or overdue;
2. SPEC-29 warning;
3. SPEC-29 advisory;
4. meal preview.

At most one interruptive candidate is returned per response. Additional
candidates may remain in a non-interruptive feed later, but the first client
slice must not stack banners.

Dismissal remains client-local until the server-side interruption ledger in
SPEC-27 exists. The client sends dismissed IDs on refresh or suppresses them
locally; it must not show a dismissed deterministic ID again.

## Freshness and caching

- Route evidence used for a due departure reminder: at most 5 minutes old.
- Weather evidence: use the existing SPEC-29 forecast validity window.
- Curated signature dish: no popularity claim and no fabricated freshness.
- Review-derived dish claim: freshness follows its SPEC-17 attribute registry
  horizon.
- Provider responses are cached by provider, rounded origin/destination,
  transport mode and departure-time bucket.
- Only the next eligible transition receives a route request. Do not fan out
  traffic calls across the whole itinerary.

## Privacy, cost and battery constraints

- No continuous or background GPS.
- The first slice derives origin from the itinerary.
- A future foreground location is optional, consented, ephemeral, and not
  persisted in notification evidence beyond the coarse `origin_basis`.
- No LLM call occurs during notification evaluation.
- Route and weather providers sit behind injectable interfaces.
- Provider keys and raw provider payloads never cross to the client.

## In-app client (Phase A2)

The backend already decides eligibility, expiry, copy, and evidence. The
client does not recompute traffic, rain, or departure time. It fetches,
filters, and renders.

### Fetch and refresh

- Call `GET /api/v1/trip/{trip_id}/notifications` for the open trip.
- Triggers: itinerary screen open, pull-to-refresh / existing alerts refresh
  control, and app resume with the same 15-minute debounce used by SPEC-29.
- Fetch is non-blocking. The itinerary renders without waiting.
- 401/403 never fall back to cache.
- Network failure or HTTP 503 may use an unexpired identity-scoped cache.
- JSON/parse errors do not silently use stale cache.
- `status: partial` with an empty list is a valid empty state, not an error.
- `status: unconfigured` is silent: no banner, no error colour.

### What may be shown

- Render at most one `departure_reminder` whose `expires_at` is still in the
  future and whose `notification_id` is not dismissed.
- Ignore `meal_preview` in this slice even if the payload later contains one.
- Use server `title` and `message` exactly. Do not rewrite, localise, or
  append invented traffic/rain sentences.
- Provenance caption may name `evidence.route.source` and, when present,
  `evidence.weather.source`. Do not display raw provider payloads or API keys.
- Do not claim `current traffic` in client chrome unless
  `evidence.route.traffic_duration_minutes` is present.

### Stacking with SPEC-29

The itinerary has one interruptive slot above the timeline.

1. If a visible departure reminder exists, show it and hide SPEC-29 weather
   cards for that paint.
2. Otherwise keep the existing SPEC-29 alert cards unchanged.

Do not stack a departure banner on top of weather cards. Trip-critical
leave-now copy is not gated by the SPEC-22 question-card daily cap.

### Dismissal and cache

- Dismiss is local, identity-scoped, persisted in SQLite.
- Use a dedicated `notification_dismissals` table keyed by
  `(identity_scope, notification_id)`. Do not mix these IDs into
  `alert_dismissals`.
- A dismissed ID stays hidden across resume and process restart.
- Cache the last successful notifications JSON with `expires_at` taken from
  the candidate, or one hour from cache time when the list is empty.

### Actions

- Close dismisses the candidate.
- Tap may scroll the timeline to `node_id` when that node is on screen.
  If the node is absent, tapping is a no-op.
- Tap does not open maps, request location, swap, cancel, or emit a
  structural event.
- Deep-link strings are stored for later SPEC-27 use; this slice does not
  register a public route for them.

## Delivery phases

1. **Phase A - departure backend:** DONE in PR #50. Endpoint, deterministic
   evaluator, cached route adapter, departure reminder, weather reuse.
2. **Phase A2 - in-app client:** DONE in PR #52. Flutter fetch, cache, local
   dismiss, and a single departure banner on the itinerary. No meal copy, GPS,
   or push.
3. **Phase B - meal evidence:** stored editorial provenance for guide-signature
   dishes and SPEC-17 `popular_dish` claims populated through SPEC-19 licensed
   corpus mining. Only then can meal previews be returned.
4. **Phase C - OS push:** scheduled watcher and delivery through SPEC-27 device
   tokens and the server-side interruption ledger. Phase C reuses the same
   candidates and does not create a second evaluator.

## Explicit non-goals

- Automatic move, swap, cancel, booking, or itinerary mutation.
- Turn-by-turn navigation.
- Scraping or storing Google/TripAdvisor review text.
- Claiming a curated signature dish is objectively the most popular.
- Synthetic traffic or random route variance in user-facing copy.
- Continuous location collection.
- Marketing, affiliate, or sponsored notifications.

## Required implementation proofs

- Only the next pending, non-skipped node is evaluated.
- Catalog 09:00 is constructed in the region timezone and stored as the
  correct UTC instant.
- Missing/unknown `schedule_basis` suppresses departure.
- Copy formats departure time in the destination region timezone, independent
  of server or device timezone.
- Missing destination or credible origin coordinates suppresses departure.
- Traffic duration is used once; no second peak-hour multiplier is applied.
- Rain adds the declared policy buffer without changing the provider duration.
- Stale or failed route evidence suppresses departure but not meal preview.
- A signature-only dish renders `signature dish in our guide` and never
  `popular`.
- A review-derived popularity claim without two independent licensed sources
  is suppressed.
- Missing SPEC-17 provenance suppresses the dish rather than displaying a bare
  value.
- Repeated evaluation returns the same deterministic ID.
- Rescheduling the node changes the ID and eligibility time.
- A due departure reminder wins over a simultaneous meal preview.
- No evaluator calls an LLM or mutates the trip.
- A traveller cannot read another traveller's notification candidates.
- The itinerary client shows at most one departure banner and does not stack
  it with SPEC-29 weather cards.
- Dismissed notification IDs remain hidden after resume.
- Client copy equals server `title`/`message`; meal_preview is ignored.

## Acceptance

- [ ] Read-only owner-scoped notifications endpoint
- [ ] Region-local catalog creation writes UTC instants and marks
      `schedule_basis: region_local_v1`
- [ ] Legacy ambiguous trips fail closed rather than receiving departure copy
- [ ] Typed `departure_reminder` and `meal_preview` response models
- [ ] Provider-backed, departure-time-aware route adapter with five-minute
      cache
- [ ] Existing SPEC-29 weather evidence reused rather than fetched through a
      second weather path
- [ ] Deterministic eligibility, expiry, identity and priority
- [ ] Partial provider failure represented without failing unrelated candidates
- [ ] Signature-dish copy is distinct from review-derived popularity copy
- [ ] SPEC-17 envelope required for review-derived dish claims
- [x] No background GPS, LLM, mutation, reroute quota, or push transport
      (Phase A backend)
- [x] Phase A2 itinerary banner fetches `/notifications`, caches, dismisses
      locally, and never stacks with weather cards
- [ ] Phase C explicitly routes through SPEC-27 rather than bypassing it
