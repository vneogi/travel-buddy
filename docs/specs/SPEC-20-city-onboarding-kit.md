# SPEC-20: City Onboarding Kit

> Status: SPECIFIED. Not implemented. Depends on SPEC-13 and SPEC-17.
>
> Deliberately smaller than the version discussed before SPEC-18 existed. The kit
> seeds a city's spine; the long tail arrives from travellers.
>
> No migration number is claimed. Numbers are taken at implementation time.

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

## Tests

- A candidate pull for a known bounding box returns venues with source, external
  identifier and local name populated, none of them `generated`
- `validate_city` fails on each refusal condition, one test per condition
- A vocabulary term absent from `taxonomy_term` blocks the load
- Coordinates outside the region bounding box block the load
- A localized value with no source blocks the load
- A price with no currency blocks the load
- The round-trip helper leaves a curated file byte-identical
- Subjective fields land as claims, not as venue columns
- A city whose language uses Latin script onboards with no driver-card data at all

## Acceptance

- [ ] Candidate puller producing a sourced spine for a region from its registry row
- [ ] `validate_city` refusing on every listed condition, one test each
- [ ] Subjective fields written as `attribute_claim` under SPEC-17
- [ ] Output consumed by the existing loader, no second write path
- [ ] Bangkok onboarded end to end as the acceptance case, effort recorded
- [ ] Suite green (R8); verified from `origin/main` (R10)
