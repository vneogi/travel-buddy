# Market strategy: the India-first corridor

> Status: DECIDED Aug 2026. Owner: Vikrant.
>
> This extends `docs/VISION.md` section 3, "who we're for and where we start".
> It does not replace the vision. The on-trip wedge, the offline stance, the
> behavioural-signal moat and the deep-over-wide rule are all unchanged. What
> this document decides is *which traveller* the product optimises for, and
> which cities follow Laos.
>
> Laos in Oct 2026 is unaffected. It is a field test of the engine, not a
> market entry. Nothing here moves that date or expands that scope.

## The decision

Optimise for the **Indian outbound traveller**, and expand along the corridor
that traveller actually flies.

## Why this is a focusing decision rather than a market grab

The original framing offered a choice between competing in Southeast Asia and
opening a less contested region such as Central Asia, the Caucasus or the
Balkans. Choosing a traveller instead of a region dissolves that trade-off.

The top outbound destinations for Indian travellers span three regions at once:
Dubai and the Gulf, Bangkok, Singapore and Kuala Lumpur in Southeast Asia, and
Baku, Tbilisi, Almaty and Tashkent across the Caucasus and Central Asia. An
India-first product therefore reaches the uncontested regions *by serving its
user properly*, while still covering the Southeast Asian cities through a lens
no incumbent applies to them.

Three further reasons, in descending order of confidence:

1. **Dubai is already in the database.** The 16 original venues sit in the
   highest-volume destination on the corridor. No other choice of beachhead
   reuses existing data.
2. **The needs are specific and unserved.** Dietary constraints, vegetarian
   availability, family and multi-generational travel, and value sensitivity
   are all first-class for this traveller and generic in every incumbent.
   Section 12 of the vision already requires audience-aware recommendation;
   this gives it a concrete audience to be aware of.
3. **Distribution is plausible.** The existing tester network spans Azerbaijan,
   Singapore, the Philippines, Cambodia, Thailand, Kazakhstan and Kyrgyzstan,
   which overlaps the corridor rather than a single country.

## Competitive read, with its confidence stated

The strongest regional competitor identified is **LandedGo**, positioned around
on-the-ground Southeast Asian travel. Treat the specifics as unverified: this
assessment comes from market research and the founder's own read, not from using
the product. What matters strategically is not the feature comparison but the
geography. A competitor concentrated in Southeast Asia does not follow an Indian
traveller to Baku, Tbilisi or Almaty.

The conclusion to *avoid* is that this is a reason to leave Southeast Asia. The
corridor includes Bangkok and Singapore because the traveller goes there. Ceding
those cities would cede the highest-volume legs of the corridor.

The honest risk, recorded in vision section 15, still stands: India as a *home*
market is contested, and a competitor holding a state tourism partnership owns a
physical point of intent that we do not. That assessment was about serving
travellers *inside* India. This decision is about serving Indian travellers
*abroad*, which is a different and less contested position.

## The corridor: six cities after Laos

Dubai, Bangkok, Singapore, Baku, Tbilisi, Almaty.

Chosen deliberately to stress the region model early: three scripts, three
currency regimes, and wildly different transport norms, at the point when fixing
the model is still cheap. A corridor of six similar cities would have taught us
nothing and hidden every assumption until it was expensive.

This does not violate the deep-over-wide rule in vision section 6. The rule
forbids chasing city count before retention exists. Six cities is the target the
*pipeline* is built for, not a launch checklist. Adding a city must become a row
in a table plus an ingestion run, which is exactly what SPEC-13 makes true.

## What this changes in the build

Four consequences, ordered by how expensive they get if deferred.

**Localized names become language-keyed, with provenance.** A single
`name_local TEXT` column encodes an assumption that every venue has exactly one
local name. That holds in Laos and breaks in Dubai, which needs Arabic and
English, and in Kuala Lumpur, which needs Malay, Chinese and Tamil. The corridor
also introduces a second axis: the driver needs Thai or Arabic or Georgian, while
the traveller may want the same venue described in Hindi or Tamil. That is a
language-keyed map, not a column. See SPEC-12.

**Every localized name carries a source.** Twelve Lao-language fields in the
curated data contain the wrong script entirely, which is what a generated name
looks like when it fails. Recording whether a name came from Wikidata, OSM, an
official listing, a human, or a model lets the driver card refuse to present an
unverified generated name as authoritative. This is rule R6 applied where it
matters most: showing a driver a name a model invented is worse than showing
English, and today nothing in the schema can tell the two apart.

**Region becomes an entity.** SPEC-13. Adding a city currently requires a code
change, and `geo_region` is an unconstrained string.

**The dietary model becomes a safety requirement.** SPEC-14. This is the
sharpest differentiator for the chosen traveller and simultaneously an open
safety hole, since halal is documented as not enforced against pork today.

## Data sourcing: open sources, not scraping

The question was whether venue data can be taken from free apps or government
sites to get off the ground. Do not scrape commercial apps: it is a terms-of-
service and legal problem with no strategic upside, and the data is not better
than the alternatives. Two open sources are genuinely better than hand curation,
and both solve the script-contamination problem at its root by supplying names
that are *sourced* rather than generated.

| Source | What it gives | Licence | Caution |
|--------|---------------|---------|---------|
| Wikidata | Multilingual labels for most notable places, via a real API | CC0 | Thin coverage for small businesses |
| OpenStreetMap | `name:lo`, `name:th`, `name:ar` tags, landmark geometry | ODbL | Attribution required; share-alike affects derived databases |
| National tourism boards | Official names and listings | Varies, check per site | Terms differ by country; verify before use |

Read the ODbL share-alike terms before deriving a database from OSM rather than
after. Neither source replaces curation for small restaurants, which is exactly
where hallucinated local names hide and where a wrong name on a driver card does
the most damage.

## What is explicitly not decided here

- **No India-domestic product.** This serves Indian travellers abroad. Serving
  travellers inside India is a different market with a different competitive
  picture, and vision section 15 already argues against chasing it in 2026.
- **No launch commitment for any corridor city.** The corridor sets what the
  pipeline must support, not what ships.
- **No change to the Oct 2 Laos scope.** Both new specs are post-Laos.
- **No pre-trip or booking-funnel expansion.** Vision section 6 still wins over
  the Part III hypotheses.
