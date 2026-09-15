# SPEC-13: Region and locale registry

> Status: SPECIFIED. Not implemented. Post-Laos.
>
> No migration number is claimed. Numbers are assigned at implementation time.
> SPEC-44 makes this registry a hard dependency before Bangkok or any other
> second-city pack is loaded.
>
> Driver: `docs/MARKET_STRATEGY.md`. This is the scalability requirement of the
> corridor made concrete.

## Goal

Make a region a real entity rather than a free-text string, so that adding a
city is a row plus an ingestion run instead of a code change.

## The problem, stated precisely

`geo_region` is a bare `TEXT` column on `venues_rag` and a string on the trip.
No table constrains its values and no code enumerates them. Three consequences,
all of which have already cost time or will:

1. **A typo yields an empty result set, not an error.** Searching a
   misspelled region returns no venues, which is indistinguishable from a
   region that is genuinely empty. The loader's region inference has already
   produced one defect of exactly this shape.
2. **Per-region facts have nowhere to live.** Fare bands, currency, tipping
   norms, emergency numbers and the local language are all per-region and are
   currently either absent or destined for a hand-edited Python dict.
3. **Language is not derivable from region in code.** SPEC-12 needs to know
   which language a driver in this city reads, in what priority order, before
   it can choose which localized name to render.

## Design decisions

1. **A `region` table, with `venues_rag.geo_region` as a foreign key.**
   The foreign key is the point: it converts a silent empty result into a
   constraint violation at write time. Adding the key requires that existing
   values be reconciled first, which is itself worth doing, since nothing has
   ever validated them.

   Country-level defaults may live in a small `country_profile` row keyed by
   ISO 3166-1 alpha-2, with explicit region overrides. A city remains the
   scheduling and catalog boundary; a country default is never silently used
   when the region declares a different value.

2. **Fields, chosen because something downstream already needs each one.**

   | Field | Needed by |
   |-------|-----------|
   | `region_key`, `city`, `country`, `country_iso` | identity, display, joins |
   | `timezone` | the scheduler, which currently assumes one offset |
   | `bbox_south`, `bbox_west`, `bbox_north`, `bbox_east` | city-pack discovery and coordinate refusal |
   | `default_lat`, `default_lng` | explicit map/search fallback, never another city |
   | `currency`, `currency_exponent`, `typical_meal_cost_band` | cost intelligence, vision section 20 |
   | `languages` (ordered) | SPEC-12, to pick which localized name to show |
   | `primary_script`, `unicode_blocks` | the script guard on curated data |
   | `fare_band_base`, `fare_per_km` | SPEC-12 driver-card fare band |
   | `emergency_numbers` | the Offline Vault, SPEC-04 |
   | `tipping_norm`, `payment_norms` | cost intelligence; includes UPI acceptance |
   | `transport_modes` | local transport intelligence, vision section 21 |

   `languages` is ordered because priority matters and is not alphabetical: a
   driver card in Kuala Lumpur should try Malay before Tamil. `payment_norms`
   carries UPI acceptance because it is a genuine differentiator for the
   corridor's traveller and changes fast enough to belong in data.

3. **The registry ships to the client and is cached.** Every consumer named
   above is reachable offline, so a region that only exists server-side is
   useless at the moment it is needed. It is small, slow-changing reference
   data, which is the easy case for caching.

4. **Unregistered regions degrade loudly.** An unknown region key yields a
   named fallback and a log line, never a silent default. A silent default here
   would present a Laos fare band to a traveller in Dubai, which is worse than
   presenting nothing.

5. **No geometry, no polygons, no PostGIS.** Region is an administrative label
   for grouping venues and holding facts. Vision section 30 defers PostGIS
   until venue count forces it, and nothing in this spec changes that.

6. **The registry replaces mirrors rather than creating another one.**
   `config/regions.py`, Flutter `RegionDefaults`, currency/language dictionaries,
   loader bounding-box branches, and advertisement allowlists stop being
   independent authorities. The server publishes one versioned projection and
   the client caches it for offline use.

7. **Unknown means refusal, never Dubai or Laos.** An unregistered key, missing
   bounding box, invalid IANA timezone, or incomplete currency convention blocks
   a city-pack load. Search and Ask return a typed unsupported-region treatment.
   No write-adjacent path may default `geo_region` to another city.

8. **Registry and pack revisions are distinct.** The registry projection carries
   its own revision. A city catalog and its pack schema carry separate revisions
   under SPEC-20. Search, caches, recommendation decisions, and acceptance
   goldens record the revisions they used.

## Tests

- A region key absent from the registry fails at write time rather than
  returning an empty search result
- Every distinct `geo_region` value present in `data/` and in the live table
  resolves to a registry row, asserted over the data rather than a fixture
- `languages` round-trips as an ordered list, and order is asserted
- Fare band resolves per region; an unregistered region returns the named
  fallback and logs, proven by asserting on the log rather than the return value
  alone
- The registry resolves from cache with the API client stubbed to throw on any
  call, per R7
- Bangkok coordinates outside the current Laos-wide bounds are accepted by the
  Bangkok row, while Hanoi coordinates cannot pass by accidentally matching a
  Laos fallback
- a region with an invalid IANA timezone or currency exponent is refused
- Python, loader, and Flutter consumers resolve the same versioned projection;
  a hand-added mirror makes the drift test fail
- Migration is additive: no `DROP`, no `RENAME`, no type change on existing
  columns

## Acceptance

- [ ] `region` table in the next migration assigned at implementation, seeded
      with the three Laos regions and Dubai, additive-only proven by grep
- [ ] country ISO, city bounding box, explicit default point, IANA timezone,
      ordered languages, script guard, currency exponent, payment/fare context,
      and transport modes are representable
- [ ] Existing `geo_region` values reconciled against the seed, with the
      discrepancies listed rather than silently corrected
- [ ] `venues_rag.geo_region` foreign key added, or the reason it cannot be
      recorded with the blocking rows named
- [ ] `config/regions.py` reads the registry rather than hardcoding, or is
      deleted if it becomes redundant
- [ ] Registry cached client-side; offline resolution proven by a test that
      fails if a network call occurs
- [ ] Unregistered region degrades loudly, with a test
- [ ] independent Python/Dart dictionaries, loader bounds, and advertisement
      allowlists no longer act as sources of truth
- [ ] SPEC-20 can validate a pack entirely from the registry projection
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10)
