# SPEC-12: Show Driver Cards (Offline)

> Status: SPECIFIED. Not implemented. Not blocked on curation -- see the
> corrected finding below.
>
> Migration numbering: the column additions below are migration `0011`, shared
> with the schema-drift fix. `driver_card_shown` is `0014`, after 0012 (booking
> anchors) and 0013 (preference_choice).
>
> Depends on SPEC-13 for the ordered language list and the fare bands. The
> interim arrangement until SPEC-13 lands is in design decision 4.
>
> Driver for the localization model: `docs/MARKET_STRATEGY.md`.

## Goal

A full-screen card the traveller shows a driver: venue name in large native
script, nearest landmark, coordinates, and a fair-fare band. Fully functional
with the radio off. This is VISION section 26, and the concrete form of
capability 7 in section 11.

## Corrected finding: the data exists, the loader discarded it

An earlier revision of this spec stated that no Laos venue carried Lao script
and that curating 58 of them was the critical path. Both claims were wrong, and
they were written without reading the data files.

Every one of the 58 curated Laos venues already carries three relevant fields,
and a fourth this spec did not know about:

    "name": "Wat Si Saket",
    "name_local": "<Lao script>",
    "nearest_landmark": "Corner of Lane Xang Avenue and Setthathirath Road",
    "nearest_landmark_local": "<Lao script>"

`nearest_landmark_local` is the most valuable field on the card. The landmark
in Lao is what the driver reads; the English landmark is for the traveller.

What was actually broken is the loader. `scripts/load_venues.py` wrote none of
these keys to `venues_rag` and ignored any JSON key outside its write set
without comment, so four curated fields per venue were lost on every load and
nothing errored. That defect is now closed, along with a guard against silently
dropped keys.

This is rule R9 in a sharper form than the rule currently states. The schema
could not express the fact, and rather than failing, the loader behaved exactly
as though the fact had never been provided. A missing column at least breaks a
write; a silently ignored key produces a successful load and a quietly poorer
product.

**Correction on `micro_location`.** A previous revision listed it among the
dropped fields. That was wrong. It is defined in `0001` as `TEXT NOT NULL` and
has been written by the loader since day one. Four fields were being discarded,
not five: `name_local`, `nearest_landmark`, `nearest_landmark_local` and
`wheelchair_notes`.

The remaining human task is verification, not entry. That verification has now
been run against Wikidata and OpenStreetMap, and the results are recorded in
`data/laos_name_verification.json`. They are worse than this section previously
assumed, in three ways.

**Coverage is low.** Ten of 58 venues can be confirmed against an external
source. Four more have a candidate that needs a human. The remaining 44 have no
external record at all and stay `generated` indefinitely. The earlier assumption
that temples and landmarks would be broadly present in Wikidata did not hold:
Laos has only a few hundred items carrying paired English and Lao labels. OSM
has better coverage but usually writes the `name` tag in Lao script, so there is
no string to match against until you bridge through `name:en`.

**Half of what can be checked is wrong.** Of the ten verifiable names, three
were exactly right, two differed only in spacing, and five were genuinely
incorrect. There is no reason to think the 44 unverifiable names are better than
the ten that could be checked. This is the honest basis for the card's
behaviour, and it is why decision 3 exists.

**Three error classes, all the same disease.** The generator was leaking Thai
and Chinese orthography into Lao:

| Error | Count | Detectable by a script guard |
|-------|-------|------------------------------|
| `U+9910 U+5385` appended, Chinese for "restaurant", in Chinese word order | 7 | Yes |
| Thai `rim` where Lao writes `him`, "beside" -- same word, wrong script | 4 | Yes |
| Thai-style `phra` cluster where Lao writes `pha` | 4 | **No** |

The corrected count for the first two is 11 fields, not the twelve previously
recorded here. The third class is the important one and vindicates the warning
this section already made: `ro` is a perfectly valid Lao letter, so the string
sits entirely inside the Lao codepoint block and no range guard can ever flag
it. It was found only by comparing against a real source, on `Haw Phra Kaew` and
`Pha That Luang`, and then applied to `Wat Phra Bat Tai` on the same
orthographic grounds. A script guard is necessary and is not sufficient.

## Design decisions

1. **Localized names are language-keyed, with provenance.** A single
   `name_local TEXT` column asserts that every venue has exactly one local name.
   That is true in Laos and false in Dubai, Kuala Lumpur and Singapore. The card
   also has two sides: the driver needs the local script, while the traveller may
   want the same venue in their own language. Both are maps from language to
   name, so `0011` carries `names_local` and `landmarks_local` as `JSONB` rather
   than `name_local` and `nearest_landmark_local` as `TEXT`:

       "names_local": {
         "lo": {"value": "<Lao script>", "source": "generated"},
         "th": {"value": "<Thai script>", "source": "wikidata"}
       }

   Keys are BCP-47 language tags. `nearest_landmark` stays `TEXT` because it is
   the English landmark for the traveller, not a localization.

2. **Every localized name records where it came from.** `source` is one of
   `wikidata`, `osm`, `official`, `manual`, `field_verified`, `generated`. This
   is a closed vocabulary and a test enforces it. `field_verified` means a human
   stood in front of the place and confirmed the name against the signage, which
   is the only source that outranks Wikidata for a small restaurant, because no
   open dataset will ever carry one. The `source` field exists because nothing
   else in the schema distinguishes a verified name from one a model invented,
   and the contamination above proves the distinction is real. All
   existing Laos values load as `generated`, because they are: they came from a
   model, and recording them as anything else would launder their origin.

3. **The card will not present a `generated` name as authoritative, and it asks
   the traveller to fix it.** A verified name renders large, in local script, as
   the primary element. A `generated` name renders visibly marked as unconfirmed
   -- smaller, with the roman name and coordinates alongside -- never as the
   confident headline. This is rule R6 applied to data: showing a driver a name a
   model made up is worse than showing English, because a wrong name burns the
   interaction instead of degrading from it.

   Refusing to vouch for 44 of 58 venues would leave the card mostly useless, so
   the unconfirmed state carries a one-tap affordance: *does the sign say this?*
   Confirm promotes the entry to `field_verified` with the confirming device
   recorded. Reject drops the card to explicit degradation for that venue, which
   is decision 8, without mutating the stored value -- see decision 11 for why.

   This is deliberate. The Oct 2 Laos trip is the only occasion on which anyone
   associated with this product will stand in front of these 58 places, and the
   verification a traveller performs by looking up at a sign is stronger evidence
   than any dataset. Verification is therefore a capture surface rather than a
   blocking prerequisite, which is the same argument the product makes everywhere
   else: observe what the traveller actually does instead of asking them to fill
   in a form first. It also means the card improves through use rather than
   waiting on a curation backlog that has no owner.

4. **Language selection comes from the region.** SPEC-13 supplies an ordered
   language list per region, and the card walks it, taking the first entry
   present in `names_local`. Until SPEC-13 lands, the loader uses a documented
   interim mapping for the three Laos regions plus Dubai, in one place, marked as
   superseded by SPEC-13 so it is deleted rather than accumulated.

5. **Applying `0011` is gated on a live-schema diff.** The loader has been
   writing columns no migration declares, and those writes have been succeeding,
   which means the columns exist. PostgREST rejects writes to columns absent from
   its schema cache, so the live schema was almost certainly edited by hand in
   the dashboard, to an extent nobody has measured. This matters concretely: if
   `name_local TEXT` already exists there, then `ADD COLUMN IF NOT EXISTS
   names_local JSONB` adds a second, empty column and silently leaves the
   hand-made one populated and unread. Dump the live schema, diff it against the
   migration set, and write the backfill before applying, not after.

6. **Fare bands are per-region, not per-venue.** They live in the SPEC-13
   registry. Curating one fare table per city is tractable; curating a fare per
   venue is not, and it would be stale by October anyway.

7. **The card renders entirely from the offline cache.** It reads the
   `cache_place` table that SPEC-02 already created. When a trip loads, pre-cache
   `names_local`, `nearest_landmark`, `landmarks_local` and coordinates for every
   node. If the card needs a network call it has failed at its only job.

8. **Degrade explicitly, never blankly.** With no usable local name, the card
   states that none is available and shows the roman name plus coordinates,
   rather than rendering an empty box. A visible degradation beats a silent one.

9. **Optimise for a stranger reading it at arm's length in sunlight.** Maximum
   type size, maximum contrast, no app chrome. Include an explicit "screenshot
   this" affordance, because a screenshot survives a dead app, battery saver, and
   a crash -- the failure modes that matter when stranded.

10. **New signal type `driver_card_shown`**, client-emittable, `value_json` of
    `{place_ref, was_offline, name_source}`. This is the only way to learn
    whether the Vault is actually used, which is the bet in section 11 capability
    7. `name_source` is included so it is possible to ask later whether generated
    names correlate with a worse outcome. It queues offline and syncs later,
    which is also a neat proof that offline capture works. Registry plus migration
    `0014` in the same commit (R5).

11. **New signal type `name_confirmed`**, client-emittable, `value_json` of
    `{place_ref, lang, shown_value, verdict}` where `verdict` is `confirmed` or
    `rejected`. Emitted by the affordance in decision 3. It queues offline like
    any other signal, which matters because the traveller is standing in the
    street when they tap it. Registry plus migration `0014` in the same commit as
    `driver_card_shown` (R5).

    A confirmation promotes `source` to `field_verified` on sync. A rejection
    must not silently delete curated data: it sets the entry aside for review
    rather than dropping it, because one traveller misreading a sign should not
    erase a name for everyone. Two independent rejections is a stronger rule than
    one, but the Oct 2 trip has a single traveller, so for now record the
    rejection and degrade the card locally without mutating the shared value.

12. **A disclaimer ships with the card**, consistent with SPEC-14. Venue data is
    curated and partly model-generated, and the card is an aid rather than an
    authority.

## Tests

- Migration `0011` is additive only: no `DROP`, no `RENAME`, no type change.
  Grep the file to prove it.
- The loader's actual payload key set equals `VENUES_RAG_WRITE_COLUMNS`, asserted
  against a record built by the loader rather than against the constant. The
  existing guard compares the data's keys to the declaration, which is why it
  passed while four fields were being dropped. Scope the assertion to the
  `venues_rag` payload; the `venue_dish` insert sits in the same function.
- `names_local` round-trips as JSONB, including the multi-language case and the
  empty case
- A name with `source: generated` does not render as the authoritative headline;
  a `wikidata` name does. Assert on rendered output, not on the model.
- Language selection follows the region's ordered list, and falls back to the
  next entry when the first is absent
- Card renders from the SQLite cache with the API client stubbed to throw on any
  call -- this is the test that proves offline, per R7, and it must fail if a
  network call is introduced
- No usable local name produces the explicit degraded card, asserted on rendered
  text
- `driver_card_shown` persists to the outbox while offline and syncs on
  reconnect
- Fare band resolves per region, with a named fallback for unregistered regions
- Drift guard green for `driver_card_shown` and `name_confirmed`
- A `generated` name renders the unconfirmed treatment and the confirm
  affordance; a `field_verified` name renders neither
- Confirming emits `name_confirmed` with `verdict=confirmed` and promotes the
  entry to `field_verified`; rejecting emits `verdict=rejected`, degrades that
  card locally, and leaves the stored value unchanged
- Both verdicts persist to the outbox while offline
- The loader applies `data/laos_name_verification.json`: the ten verified names
  land with their recorded source and ref, the three token corrections are
  applied, and no token correction changes a `source` value
- No `name_local` or `nearest_landmark_local` field contains a codepoint outside
  the Lao block, asserted over every venue JSON. This guard cannot catch the
  `phra` class, and a comment in the test says so, so that nobody later mistakes
  a green run for verified data

## Acceptance

- [ ] Migration `0011` carries `names_local` and `landmarks_local` as JSONB;
      additive-only proven by grep
- [ ] Live schema dumped and diffed against the migration set, with the manual
      columns listed, before `0011` is applied
- [ ] Backfill written for any hand-made `name_local` column found by that diff
- [ ] Loader writes the language-keyed shape with `source` on every entry;
      existing Laos values recorded as `generated`
- [ ] Payload-versus-declaration test in place, proven by removing one field and
      watching it fail
- [ ] A count query proves zero venues without a usable local name across the
      three Laos regions after a re-load
- [ ] `data/laos_name_verification.json` applied by the loader, with the ten
      verified entries carrying source `wikidata` or `osm` and a resolvable ref
- [ ] Lao-script guard test in place, with its blind spot documented in the test
- [ ] The card ships the unconfirmed treatment and the confirm affordance, so the
      Oct 2 trip returns `field_verified` names rather than only telemetry
- [ ] A sample of Lao script verified against an independent source, with the
      sample size, the result, and the resulting `source` values recorded
- [ ] Fare bands present for the three Laos regions
- [ ] Card works with the radio off, proven by a test that fails if any network
      call occurs
- [ ] Generated names never render as authoritative, with a test
- [ ] `driver_card_shown` in registry plus migration `0014`; drift guard green
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10); R1 grep clean
