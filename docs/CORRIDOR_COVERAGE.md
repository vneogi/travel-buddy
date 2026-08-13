# Corridor Data Coverage

> Measured 13 Aug 2026 against the OpenStreetMap Overpass API. Raw numbers in
> data/corridor_coverage.json. Re-runnable; the query is recorded below.
>
> This exists because a city-onboarding pipeline was about to be designed on an
> assumption -- that external sources cover the corridor cities much better than
> they cover Laos. The assumption holds, but not uniformly, and two of the
> conclusions were not the expected ones.

## What was measured

For a central bounding box per city, every OSM node, way and relation tagged
`tourism`, `historic`, or `amenity` in (restaurant, cafe, bar, marketplace).
For each, whether it carries a name, an English name, a local-language name, and
a `wikidata` identifier.

The column that matters is **bridgeable**: the venue has a usable local-script
or local-language name *and* something English to match it against. That is the
set a curator can pull from with provenance already attached. Counting only
`name:xx` tags undercounts badly, because OSM usually puts the local script in
the plain `name` tag -- the exact trap that made the Laos verification pass look
like a failure.

## Results

| City | Local script | POIs | Named | Bridgeable | Wikidata id |
|---|---|---|---|---|---|
| Bangkok | Thai | 10235 | 6611 | 1856 | 191 |
| Singapore | Chinese | 7481 | 6554 | 820 | 166 |
| Kuala Lumpur | Latin | 2734 | 2617 | 325 | 47 |
| Phuket | Thai | 3974 | 2589 | 229 | 9 |
| Dubai | Arabic | 2577 | 2198 | 206 | 166 |
| Ho Chi Minh City | Latin | 3857 | 3018 | 164 | 27 |
| Hanoi | Latin | 2889 | 2219 | 148 | 32 |
| Vientiane | Lao | 1342 | 960 | 142 | 11 |
| Da Nang | Latin | 2234 | 1919 | 81 | 3 |
| Luang Prabang | Lao | 837 | 505 | 49 | 5 |

## Three conclusions

### 1. Laos was at its ceiling, so do not generalise from it

Luang Prabang has 505 named POIs in the whole town and 49 that are bridgeable.
SPEC-08 curated 58 venues, which means the curation had already exhausted what
OSM knows about the place. Ten verifiable names out of 58 was the town's data
ceiling, not a defect in the verification method. Bangkok's 1856 is roughly
thirty-eight times as many.

The practical consequence: the effort Laos took is not the per-city cost. Most
of that effort went into discovering that the data was generated, unprovenanced
and contaminated, and into building the guards that now catch all three.

### 2. Source-first works, but only for the identity layer

Sampling which fields OSM can actually fill, for the four cities where it was
measured:

| Field | Bangkok | Singapore | Kuala Lumpur | Dubai |
|---|---|---|---|---|
| address | 30% | 47% | 39% | 46% |
| cuisine | 30% | 38% | 24% | 20% |
| website or phone | 22% | 25% | 20% | 21% |
| opening hours | 16% | 19% | 16% | 15% |
| wheelchair | 4% | 16% | 2% | 16% |
| indoor or outdoor | 4% | 10% | 4% | 13% |
| air conditioning | 3% | 6% | 3% | 13% |
| price band | 0% | 0% | 0% | 0% |

So the layers separate cleanly:

- **Identity** -- name, local name, coordinates, category, external id. OSM is
  strong, and this is precisely the layer whose absence was expensive. Sourcing
  it first flips the default provenance from `generated` to `osm` or `wikidata`.
- **Factual attributes** -- address, cuisine, hours, contact. Partial. Take what
  is there for free; do not depend on it.
- **Subjective** -- vibe tags, audience fit, dwell minutes, why to go, price
  band. Zero. This stays a judgement call, and `generated` is an honest
  provenance for it because no authority exists to contradict it.
- **Safety** -- diet, accessibility. Effectively absent. See below.

### 3. The safety layer has no source, and that is a real problem

`diet:halal` covers 20 of 6611 Bangkok POIs, 124 of 6554 in Singapore, 9 of 2617
in Kuala Lumpur and 130 of 2198 in Dubai. `diet:vegetarian` runs from two to
seven percent. Wheelchair information reaches 16 percent at best and 2 percent
at worst.

SPEC-14 models dietary constraints as safety filters rather than preferences,
which is the right decision for the intended traveller. But a filter needs
input, and no open dataset can supply it at the coverage a safety claim
requires. This is now recorded as a high-severity risk in PROJECT_STATUS. The
options are deliberate curation for a small set, a commercial or community feed,
or deriving it from user signals over time -- and until one exists, the feature
has to say it does not know.

## Consequence for the driver card

SPEC-12 earns its keep only where there is a script barrier. Kuala Lumpur, Ho
Chi Minh City, Hanoi and Da Nang write their names in Latin script, so a roman
name on a phone screen already works and the card adds little. It matters in
Thailand, Laos and Dubai, and would matter in Japan, China, Korea and Taiwan.

The practical rule: **the driver card must never gate adding a city.** Half the
corridor does not need it.

## Reproducing this

The Overpass query, per city bounding box:

    [out:json][timeout:90];
    (
      nwr["tourism"](S,W,N,E);
      nwr["historic"](S,W,N,E);
      nwr["amenity"~"^(restaurant|cafe|bar|marketplace)$"](S,W,N,E);
    );
    out tags;

Bounding boxes are in data/corridor_coverage.json. Overpass rate-limits, so
leave several seconds between cities and retry on HTTP errors. Counting is
done client-side: a name is treated as local-script when it contains codepoints
from the city's expected Unicode block, which is why the Latin-script cities
report zero there and are counted through their `name:xx` tags instead.
