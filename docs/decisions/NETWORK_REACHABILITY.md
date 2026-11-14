# Decision: network reachability (Google Isochrones)

Status: PENCILED 2026-11-15. Owner accepted as a product lever for
in-trip usability and return visits. Not started. Does not reorder the
2026-11-15 to 2026-12-04 trip-critical list.

## Why

In-trip surfaces (What Now, swap, Add/Move, "keep the next booking")
all ask the same question: can the traveller actually get there in N
minutes? Today every answer uses one deterministic Haversine walk at
5 km/h (`services/transit.walking_minutes`). That is offline-safe and
SPEC-41-stable, but it ignores real paths. Dense old towns (Stone Town,
Luang Prabang) and traffic-aware car/scooter day trips are where it
lies.

Google Maps Platform Isochrones API (Preview, free during Preview;
planned GA about $3 per 1,000 requests with a 10k free monthly cap)
returns a road-network area for walk / bicycle (up to 120 min) or
drive / two-wheeler (up to 60 min), optionally traffic-aware, plus a
reverse direction ("from where can I still reach this booking"). Output
is GeoJSON. Ferries and water crossings are out of scope for the API.

## Product decision

1. Treat network reachability as an **optional enrichment layer** on top
   of Haversine, never a replacement for create/corridor packing
   determinism.
2. First consumer: SPEC-46 What Now "within N minutes" and
   `keeps_next_booking_reachable`, using **catalog or booking stop
   coordinates** as the origin (not device GPS). Device GPS stays
   SPEC-46 Phase B after SPEC-43.
3. Always name the source in the response envelope
   (`haversine_estimate` vs `network_isochrone`) so we never overclaim.
4. Offline and Preview failure fall back to Haversine with no user-
   visible error beyond the named source.
5. Not a paid feature. Accurate "can I make it?" is trust, not a
   Pro gate. Monetisation later remains sachet/affiliate at the moment
   of need (VISION / MARKET_STRATEGY).
6. Behind a swappable provider interface. Preview has no SLA; Distance
   Matrix / route-matrix remain comparison options.

## Sequence

1. Trial run (Genie brief
   `docs/briefs/GENIE_ISOCHRONE_TRIAL.md`): offline script + recorded
   fixtures compare Haversine vs Isochrones venue sets for Stone Town,
   Nungwi, and Luang Prabang at 15/30/45 min walk. Owner runs the live
   call once. Decision rule: if disagreement is material (especially
   Stone Town), the feature earns an implementation slice.
2. If earned: server provider + short TTL cache + spend accounting
   under Gap 11; wire What Now filter first, then booking-return check.
3. Later: drive/two-wheeler bands for day trips; map polygon overlay
   (maps remain deferred).

## Non-goals

- Replacing Haversine inside SPEC-41 create packing.
- Background GPS, continuous tracking, or sending device location to
  Google before SPEC-46 Phase B / SPEC-43 location proofs.
- Charging travellers for network reachability.
- Ferry routing (API limitation; keep honest unknowns).

## Spec touchpoints

- SPEC-46: What Now reasons and Phase A/B origins.
- SPEC-41: packing stays Haversine; enrichment is out of packing.
- SPEC-43 Gap 11: provider spend; Gap 9/12: no raw GPS in logs/URLs.
- `docs/HOSTED_STATE.md`: record when the API is enabled on the project.
