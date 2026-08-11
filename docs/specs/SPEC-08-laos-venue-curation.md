# SPEC-08: Laos Venue Curation

> Status: EXECUTED. This spec was written in chat, carried out in full, and
> committed here afterwards as the record. It documents what was actually done,
> including where the result diverges from what was originally proposed.

## Goal

Produce a machine-loadable venue dataset for the Laos trip that fills
`venues_rag` so the app has something real to schedule, and seeds `venue_dish`
so food signals have subjects to reference.

Without substitutable alternatives the reroute engine has nothing to offer. A
spread of one-of-each is useless: the engine needs several venues that could
plausibly replace each other.

## The rule that matters most

**Every categorical field comes from a closed vocabulary defined in this spec.**

The project has learned this three times over, with `node_skipped` reasons,
`value_kind`, and the signal type registry. The moment a field accepts free
text the data stops being analysable: `cafe`, `Cafe `, `coffee shop` and the
accented spelling are four values for one concept, and no downstream cleverness
recovers from that.

If a needed value is missing from a vocabulary, add it to the vocabulary first,
then use it. Never improvise mid-curation. The vocabulary lives in
`scripts/load_venues.py` and validation is a hard failure, not a warning.

## What was executed

Three cities, not one. This was the finding that changed the shape of the work:
the trip spans Luang Prabang, Vang Vieng and Vientiane, so coverage targets
apply per city, and inter-city transit becomes a first-class itinerary node
rather than a nice-to-have.

| File | Region | Venues |
|------|--------|--------|
| `data/laos_luang_prabang.json` | Luang Prabang | 23 |
| `data/laos_vang_vieng.json` | Vang Vieng | 15 |
| `data/laos_vientiane.json` | Vientiane | 20 |

58 venues total, carrying 44 venue dishes between them, plus 30 entries in
`data/laos_dish_glossary.json`. These sit alongside the 16 synthetic Dubai
venues, and the scheduler can route across both regions.

Region codes must match `config/regions.py` exactly. A mismatch does not error;
region filtering silently returns nothing, which is worse.

## File format

JSON, not CSV. Opening hours and dishes are nested, and flattening them into
delimited strings reintroduces exactly the parsing fragility that the JSONB
hours migration was written to remove.

Each file is a wrapper object, not a bare array:

    {
      "geo_region": "<region code from config/regions.py>",
      "curated_at": "YYYY-MM-DD",
      "curator_notes": "where the facts came from and when hours were checked",
      "venues": [ ... ]
    }

The loader also accepts `data` or `items` as the array key, and a bare array for
backward compatibility.

## Venue schema

Required. No venue loads without these:

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | As locals and signage would say it, not a brochure title |
| `micro_location` | string | Neighbourhood or landmark cluster, from a per-city closed list |
| `lat`, `lng` | float | Five decimal places. A bare float, never an array |
| `category` | enum | See vocabularies |
| `description` | string | One or two sentences. This is what gets embedded |
| `typical_dwell_minutes` | int | Guess rather than omit; the solver needs a number |
| `indoor_outdoor` | enum | Required |
| `price_band` | enum | Required |

The `description` is the highest-leverage field, because it is what the
embedding sees. Write it the way a traveller would ask for the place, not the
way a guidebook describes it. "Open-air noodle stall on the river road where
locals eat breakfast, plastic stools, cash only" retrieves well. "A charming
establishment offering traditional fare" embeds to nothing useful.

Expected and validated when present: `opening_hours_structured` (or
`opening_hours`), `vibe_tags`, `audience`, `has_aircon`, `dishes`.

Valuable and optional: `nearest_landmark` and `name_local`, both required later
by SPEC-12; `booking_required`, `source_url`, `notes`.

Never filled by hand: `venue_id` and `embedding` are generated at load,
`trap_score` is computed later, and `is_sponsored` and `bid_weight` default to
zero.

## Opening hours

    "opening_hours_structured": {
      "mon": [["09:00", "17:00"]],
      "tue": [["09:00", "17:00"]],
      "wed": [],
      "thu": [["09:00", "17:00"]],
      "fri": [["09:00", "17:00"]],
      "sat": [["09:00", "12:00"], ["14:00", "20:00"]],
      "sun": [["09:00", "17:00"]]
    }

- All seven day keys present, always. A missing key is ambiguous; `[]` is not.
- `[]` means closed that day.
- Multiple ranges mean split hours, which are common in South East Asia where
  restaurants close between lunch and dinner.
- 24-hour, zero-padded, local time. End must be later than start.
- Crossing midnight is written `[["18:00", "23:59"]]`. The scheduler does not
  need next-day precision.
- Genuinely unknown means `null` for the whole object, with a note. Never invent
  hours: a wrong "open" is worse than an honest unknown, because the scheduler
  will plan against it.

Verify hours for anything actually being visited. Temples especially, where alms
and ceremony hours differ from visiting hours.

## Dish schema

Food categories only, two to four dishes per venue:

    "dishes": [
      {
        "dish_key": "<glossary key>",
        "name_local": "<Lao script>",
        "name_roman": "<romanised>",
        "name_en": "<plain English>",
        "price_band": "budget",
        "is_signature": true,
        "notes": "what this place is actually known for"
      }
    ]

`name_local` is what makes the ordering card work, because a stall holder can
read it. `name_roman` is what you say out loud. At most one or two dishes per
venue are signature; if everything is signature, nothing is.

Dish curation finishes on the ground. Curate what can be found in advance; the
real data comes from standing in front of the stall.

## Dish glossary and allergen safety

`data/laos_dish_glossary.json` is loaded separately by
`scripts/load_dish_glossary.py`. Every check is a hard failure:

1. Required fields: `dish_key`, `name_en`, `contains`, `may_contain`,
   `suitable_for`
2. `contains` and `may_contain` validated against the allergen vocabulary
3. `suitable_for` validated against the dietary label vocabulary
4. A cross-field safety invariant: a dietary label must not contradict a
   declared allergen
5. Duplicate `dish_key` detection

The safety invariant is the reason this is a separate hard gate. A dish labelled
safe for someone that in fact contains their allergen is the one class of bug in
this project that can hurt a person.

## Coverage targets, and what was actually achieved

| Category | Target per city | Result |
|----------|-----------------|--------|
| Food: restaurant, street_food, cafe | 15-18 | Met in Luang Prabang, thin elsewhere |
| Temples, museums, culture | 6-8 | Met |
| Nature, viewpoints, waterfalls | 5-6 | Met |
| Markets, shopping, craft | 4-5 | Met |
| Massage, spa, rest | 3-4 | **Zero in Vientiane** |
| Transport hubs | 2-3 | Met |

The massage and spa gap is not cosmetic. Those venues are what the app swaps
**to** when the traveller is exhausted, so one region currently has no
fatigue-reroute target at all.

## Known deviations and open defects

These are real and tracked in `docs/AWAITING_VERIFICATION.md`:

- **`opening_hours` is null on all 58 venues.** The loader field-name fix landed
  after the data was loaded and the backfill was never re-run, so the scheduler
  has no hours to respect for any Laos venue.
- **The loader vocabularies on `main` no longer match the data.** The expansion
  that added `street_food`, `walking_area`, `river_activity`,
  `craft_workshop`, `photogenic`, `touristy`, `mobility_limited`, `mixed`,
  `splurge` and the rest was reverted by a merge. Validating the three files
  against `main` today fails on vocabulary.
- **`audience` was overcorrected.** `mobility_limited` ended up on roughly two
  thirds of venues. A tag that broad carries no information and cannot filter
  anything. Be strict: tag only what genuinely applies.
- **`has_aircon` is null nearly everywhere.** It matters more than expected for
  an October trip.
- **No venue carries `name_local` or `nearest_landmark`.** Those columns do not
  exist in `venues_rag` yet, which is the blocking finding in SPEC-12.

## Loader contract

    python scripts/load_venues.py <files> --geo-region <region> [--dry-run]

- Validates everything before touching the database, and exits non-zero on any
  error.
- Rejects a whole file on validation failure. Rows are never skipped silently.
- Upserts on `(name, geo_region)`, so re-running is idempotent.
- Dishes are inserted after venues, because of the foreign key.
- Warnings are printed and do not block: thin `micro_location` clusters, null
  hours, null `has_aircon`, food venues with no dishes, and implausible dwell
  times.

`--geo-region` is currently mandatory in practice: without it the loader raises
`NameError` on an unassigned variable. See `docs/AWAITING_VERIFICATION.md`.

## Acceptance

- [x] Three region files load with zero validation errors
- [x] 58 venues and 44 venue dishes present, with embeddings
- [x] 30 glossary entries pass the allergen safety invariant
- [x] Region codes match `config/regions.py`
- [ ] `opening_hours` backfilled and non-null across all 58 venues
- [ ] Loader vocabularies restored so the files validate against `main`
- [ ] `audience` tightened, `mobility_limited` applied only where true
- [ ] At least three massage or spa venues per city
