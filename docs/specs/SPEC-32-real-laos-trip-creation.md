# SPEC-32: Real Laos trip creation from the venue catalog

> Status: IMPLEMENTED (this branch). Device verification of a Laos create on
> Windows remains open in AWAITING_VERIFICATION.
>
> One city per trip. Create reads venues already stored for that geo_region
> and builds a deterministic 4 to 6 stop day. It does not call hybrid search,
> the LLM, reroute quota, SPEC-13 persistence, trip_stay, or a corridor trip.

## Goal

Stop stamping a Laos destination onto the Dubai fixture itinerary. A trip for
Luang Prabang, Vang Vieng, or Vientiane must be composed of that city's catalog
venues, with that city's coordinates on the trip context.

## Product decisions

1. **One city.** The create form already sends a single geo_region. This slice
   does not invent a multi-city corridor or a stay table.
2. **Catalog, not search.** `list_venues_for_region` is a filter on stored
   rows. Embeddings and hybrid_venue_search are out of the create path.
3. **Deterministic 4 to 6 stops.** Same catalog plus same city always yields
   the same venue_id sequence. Target five, never fewer than four eligible
   venues, never more than six.
4. **Refuse rather than fallback.** Unknown cities and cities without enough
   eligible venues return 422 unsupported_region. `get_region()` Dubai
   fallback is not the allowlist.
5. **Infrastructure is not a day out.** hospital, pharmacy, and transport_hub
   are stored but not selected as itinerary stops.
6. **Advertise only what we can seed.** GET /trips supported_regions lists
   cities that currently have a viable catalog, Dubai first, then the three
   Laos codes.

## Out of scope

- SPEC-13 region table
- trip_stay / multi-night hotel UI
- Removing hotel rescue
- Timezone rewrite
- LLM planner or quota on create

## Tests

- Unknown region 422, response body contains no Dubai Museum fixture name
- Empty Luang Prabang catalog is omitted from supported_regions and refused
- Each Laos city create uses only that JSON catalog, inside a Laos bbox
- Repeated creates for the same city keep venue order and venue_id
- Create does not await the LLM and does not increment daily_reroute_count
- Create does not call hybrid_venue_search
- Flutter home create posts luang_prabang_laos when that city is selected

## Acceptance

- [x] require_region raises on unknown codes
- [x] Dubai, Luang Prabang, Vang Vieng, and Vientiane seed from catalog
- [x] Dubai fixture names never appear on a Laos trip
- [x] 4 to 6 stops, no hospital/pharmacy/transport_hub
- [x] Home supported_regions matches cities we can actually create
