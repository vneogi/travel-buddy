# SPEC-34: Trip-local near-me and venue search

> Status: IMPLEMENTED (this branch). Device GPS remains out of scope.
>
> Venue search must use the trip's city. A Laos trip must not search around
> Dubai coordinates.

## Goal

Stop defaulting hybrid venue search to 25.1972, 55.2744. Near-me and
`GET /venues/search` resolve lat/lng from the loaded trip, then from known
region defaults, and refuse when neither is available.

## Product decisions

1. **Explicit coords win.** Client-supplied lat/lng are used as-is.
2. **Trip context next.** `trip_id` loads `current_context.location_lat/lng`.
   If those still look like the Dubai schema default and `geo_region` is not
   `dubai_uae`, use that region's defaults from `config/regions.py`.
3. **Refuse, do not fall back.** Unknown trip, unknown region, or missing
   coords return 422 `missing_coordinates`. `get_region()` Dubai fallback is
   not the allowlist.
4. **Client has no silent Dubai default.** `searchVenues` requires lat/lng.
   Callers take coords from TripState or `RegionDefaults.coordsFor`.
5. **No GPS.** This slice does not request device location permission.

## Out of scope

- SPEC-13 region table
- Trip-less Ask (SPEC-25 remainder)
- Windows `geo:` maps hand-off
- Hotel Rescue UI
- SPEC-32 create-trip catalog path

## Tests

- Laos trip search via trip_id succeeds without Dubai hardcoded defaults
- Dubai trip search still succeeds
- Explicit lat/lng override trip_id
- No coords and no trip_id -> 422
- Unknown trip_id -> 422, not Dubai
- Flutter RegionDefaults returns LP coords for luang_prabang_laos and null
  for an unknown code

## Acceptance

- [x] No silent Dubai default on /venues/search
- [x] Client searchVenues requires lat/lng
- [x] Unknown region does not use get_region Dubai fallback
