# SPEC-20: City Onboarding Kit

> Status: SPECIFIED. Not implemented. Depends on SPEC-13 and SPEC-17.
>
> Deliberately smaller than the version discussed before SPEC-18 existed. The kit
> seeds a city's spine; the long tail arrives from travellers.
>
> No migration number is claimed. Numbers are taken at implementation time.
> SPEC-44 makes Bangkok the acceptance case for the factory, not another
> hardcoded city exception.

## Goal

Adding a city becomes a registry row plus a seeded spine of anchor venues,
produced by a pipeline whose gate refuses bad input. Not a project.

## Why the scope shrank

The first plan had the kit enumerating a city. SPEC-18 makes that unnecessary and
probably wrong: demand is a better prioritisation function than a curator's
guess, so the kit only needs the 40 to 60 places that anchor a first itinerary --
the ones a traveller would be surprised to find missing. Everything else arrives
when somebody asks about it.

docs/CORRIDOR_COVERAGE.md establishes that this is feasible where it matters:
Bangkok has 1856 venues carrying both a local-script and a matchable English
name, against 49 in Luang Prabang. Sourcing a spine from open data is comfortable
at that density.

## Design decisions

1. **Source identity first, generate second.** Pull candidates from OSM and
   Wikidata for the region's bounding box. Name, local-script name, coordinates,
   category and external identifier arrive together, already carrying a real
   `source`. This flips the default provenance from `generated` to `osm` or
   `wikidata`, which is the whole driver-card problem solved at the source instead
   of patched at the presentation layer.

2. **The model fills only the subjective layer,** and those values enter as claims
   under SPEC-17. The coverage measurement is unambiguous here: price band is
   absent from open data entirely, and dwell time, vibe and audience fit exist in
   no dataset at all. There is no authority to contradict a judgement call, so
   `llm_generated` is an honest provenance for exactly these fields and a
   dishonest one for identity.

3. **The region registry is a hard dependency.** SPEC-13 supplies bounding box,
   languages, currency, timezone and fare bands. Without it every added city
   hardcodes something, which is the failure mode this spec exists to prevent.

4. **`validate_city` refuses rather than warns.** It fails on: a vocabulary term
   absent from `taxonomy_term`; text in the wrong script for the declared
   language; coordinates outside the region's bounding box; any localized value
   with no `source`; a missing external identifier without an explicit waiver; and
   a price with no currency. A warning gets ignored at the exact moment it
   matters -- the loader emitted 58 false warnings for weeks and masked two real
   ones.

5. **The gate cannot catch same-script errors, and says so.** A wrong vowel inside
   otherwise valid Lao passes every codepoint check, and two such errors are known
   in the current data. The gate's job is to eliminate the mechanical classes;
   SPEC-17 question cards handle the rest.

6. **The driver card never gates a city.** Kuala Lumpur, Ho Chi Minh City, Hanoi
   and Da Nang write their names in Latin script, so SPEC-12 adds little there. It
   matters in Thailand, Laos and Dubai. Half the corridor does not need it and
   must not wait for it.

7. **Reuse the curation round-trip.** `scripts/format_venue_json.py` already
   converts between the ASCII-escaped repo form and a readable copy. It was built
   for Laos cleanup and is in fact onboarding infrastructure.

8. **No new ingestion path.** The kit produces files the existing loader consumes,
   so every guard the loader carries applies for free. A pipeline writing to the
   database directly would need its own copy of all of them.

9. **Currency correctness is part of onboarding.** A city arrives with a currency
   and an explicit minor-unit convention. The existing price column documents
   itself ambiguously, and a second currency is what turns that into wrong data.

10. **A city is one versioned pack.** The repository layout is:

        packs/<country_iso>/<region_key>/
          region.json
          spine.json
          micro_locations.json
          dishes.json
          glossary.json
          coverage.json
          licence.json
          waivers.json
          goldens.json

    `region.json` is the proposed SPEC-13 row. `spine.json` retains the existing
    wrapper shape: declared region, curation time, notes, and venues. Optional
    dish and glossary files are present only when they carry real curated data.
    Every file declares a pack-schema version and the loaded catalog receives a
    catalog revision.

11. **External identity is a first-class input.** `external_ids` is a list on
    every venue rather than a side effect of a localized-name reference. OSM IDs
    retain their element type (`node`, `way`, or `relation`). Hosted upsert and
    in-memory seed use the same source/external-ID identity rule. Name plus region
    is not the durable deduplication key.

12. **One taxonomy and one loader.** The loader validates against the same
    versioned `taxonomy_term` authority the database and recommendation policy
    use. Permissive `VALID_*` supersets are not a second contract. Hosted,
    in-memory, and dry-run data pass through the same records and validation
    rules; `seed_supabase.py`, hand-built venue objects, or a direct pipeline
    writer cannot create another production vocabulary.

13. **Unknown hours are explicit and overnight hours are legal.** A missing
    source is represented as `opening_hours_structured: null`, never an invented
    `09:00-17:00` or `09:00-23:00`. The loader and SPEC-41 share the same
    seven-day, split-window, and overnight contract. A pack cannot pass dry-run
    and then be interpreted differently by the scheduler.

14. **The whole city is atomic.** Validation produces a machine-readable refusal
    report before any write. Load is idempotent by source identity and commits
    the pack revision completely or not at all. A partially loaded city is never
    advertised.

15. **Advertisement is computed, not allowlisted.** A city becomes available
    only after identity, taxonomy, licence, catalog, search, and SPEC-41 capacity
    goldens pass. `advertised_regions` does not contain a preferred hardcoded
    city list. Caches and recommendation decisions retain the catalog revision.

16. **Licence travels with the pack.** `licence.json` records source, licence,
    attribution, retrieval time, and allowed use. Any external-ID waiver is
    explicit and bounded in `waivers.json`. Obtain an ODbL position before
    distributing an OSM-derived multi-city database. Review or social sources
    excluded by SPEC-19 remain excluded.

17. **Offline maps are a later optional artifact, not city data authority.**
    After Bangkok proves the city factory, a pack may reference the manifest
    defined by SPEC-04 for a separately built offline map artifact. The manifest
    is versioned and licensed, but the binary is not required to validate,
    ingest, search, or advertise a city. Adding it must not create a second
    venue identity, taxonomy, or ingestion path. Renderer, tile format, and
    storage provider remain choices made from measured device evidence.

## Pipeline

1. Register and validate the SPEC-13 country/region record.
2. Measure OSM/Wikidata coverage inside that exact city bounding box and write
   `coverage.json`.
3. Pull identity candidates with external IDs, coordinates, source, and local
   names. Generated identity is forbidden.
4. Select a 40 to 60 venue spine against declared category and geography
   targets. Infrastructure may be present for offline use without becoming an
   itinerary candidate.
5. Add operational facts without inventing missing values. Subjective values
   enter as SPEC-17 claims.
6. Run `validate_city`. Every refusal blocks the entire pack.
7. Run the existing loader dry-run, then the same loader against hosted or
   in-memory storage.
8. Run advertisement capacity, search, Ask, and deterministic itinerary goldens.
9. Publish the new catalog revision only after all gates pass.

Bangkok is the first end-to-end acceptance city because measured open-data
coverage is materially stronger than Laos and its Thai script, overnight hours,
payment norms, transport modes, and currency exercise the template. Chiang Mai
and Pai are measured after Bangkok rather than assumed. Vietnam follows through
the same pack; Cambodia is measured before committing to an OSM-led spine; the
Philippines remains later as a UTC+8 and payment-method stress case.

No Thailand, Vietnam, Cambodia, or Philippines venue pack is ingested before the
registry, source identity, claims boundary, and refuse-not-warn gates exist.

## Tests

- A candidate pull for a known bounding box returns venues with source, external
  identifier and local name populated, none of them `generated`
- `validate_city` fails on each refusal condition, one test per condition
- A vocabulary term absent from `taxonomy_term` blocks the load
- Coordinates outside the region bounding box block the load
- A localized value with no source blocks the load
- A missing external ID without a named waiver blocks the load
- Wrapper, folder, and registry `geo_region` mismatch blocks the load
- A price with no currency blocks the load
- A currency amount whose exponent conflicts with the registry blocks the load
- A coordinate is checked against the selected region's bounds; there is no
  Dubai or Laos fallback
- A localized identity in the wrong Unicode block for the region's primary
  script blocks the load
- Missing hours remain null and are never replaced by a default
- Split and overnight windows survive loader, database, and scheduler
  round-trip with the same meaning
- A pack using a taxonomy term absent from the versioned registry is rejected
  before any row is written
- The round-trip helper leaves a curated file byte-identical
- Subjective fields land as claims, not as venue columns
- A city whose language uses Latin script onboards with no driver-card data at all
- Failure after the first proposed venue leaves zero rows for the new catalog
  revision
- Re-running the same pack is idempotent by external identity
- An invalid or partially loaded city cannot appear in advertised regions

## Acceptance

- [ ] Candidate puller producing a sourced spine for a region from its registry row
- [ ] `validate_city` refusing on every listed condition, one test each
- [ ] Subjective fields written as `attribute_claim` under SPEC-17
- [ ] Output consumed by the existing loader, no second write path
- [ ] loader, in-memory seed, and hosted load share one taxonomy, hours, identity,
      and field contract
- [ ] pack load is atomic, idempotent, revisioned, and produces a refusal report
- [ ] unknown hours stay unknown; split and overnight windows match SPEC-41
- [ ] advertisement derives from passed gates and capacity, not a city allowlist
- [ ] source, licence, attribution, retrieval date, and waiver records accompany
      every imported pack
- [ ] Bangkok onboarded end to end as the acceptance case, effort recorded
- [ ] Bangkok requires no Python, Dart, loader-bounds, currency, language, or
      advertisement exception
- [ ] Suite green (R8); verified from `origin/main` (R10)
