# SPEC-13: Region and locale registry

> Status: SPECIFIED. Not implemented. Post-Laos.
>
> Migration `0015`. Allocation: 0011 venues_rag columns, 0012 booking anchors,
> 0013 preference_choice, 0014 driver_card_shown, 0015 this, 0016 SPEC-14.
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

2. **Fields, chosen because something downstream already needs each one.**

   | Field | Needed by |
   |-------|-----------|
   | `region_key`, `city`, `country` | identity, display |
   | `timezone` | the scheduler, which currently assumes one offset |
   | `currency`, `typical_meal_cost_band` | cost intelligence, vision section 20 |
   | `languages` (ordered) | SPEC-12, to pick which localized name to show |
   | `primary_script` | the script guard on curated data |
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
- Migration is additive: no `DROP`, no `RENAME`, no type change on existing
  columns

## Acceptance

- [ ] `region` table in migration `0015`, seeded with the three Laos regions and
      Dubai, additive-only proven by grep
- [ ] Existing `geo_region` values reconciled against the seed, with the
      discrepancies listed rather than silently corrected
- [ ] `venues_rag.geo_region` foreign key added, or the reason it cannot be
      recorded with the blocking rows named
- [ ] `config/regions.py` reads the registry rather than hardcoding, or is
      deleted if it becomes redundant
- [ ] Registry cached client-side; offline resolution proven by a test that
      fails if a network call occurs
- [ ] Unregistered region degrades loudly, with a test
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10)
