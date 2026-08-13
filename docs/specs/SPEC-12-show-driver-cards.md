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

The remaining human task is verification, not entry: confirm the Lao script
against an independent source. Temples and landmarks are low risk. Small
restaurants and tour operators are where a generated transliteration can
masquerade as a real Lao name. Twelve fields in the curated data are already
known to contain the wrong script entirely -- seven `name_local` values carrying
Mandarin and five `nearest_landmark_local` values carrying Thai -- which is what
this failure looks like when it is severe enough to be detectable by codepoint
range. The ones that share a script with the target language are the dangerous
ones, because no guard will catch them.

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
   `wikidata`, `osm`, `official`, `manual`, `generated`. This exists because
   nothing in the current schema distinguishes a verified name from one a model
   invented, and the contamination above proves the distinction is real. All
   existing Laos values load as `generated`, because they are: they came from a
   model, and recording them as anything else would launder their origin.

3. **The card will not present a `generated` name as authoritative.** A verified
   name renders large, in local script, as the primary element. A `generated`
   name either degrades to English or renders with a visible caveat, never as the
   confident headline. This is rule R6 applied to data: showing a driver a name a
   model made up is worse than showing English, because a wrong name burns the
   interaction instead of degrading from it. The user can still see the generated
   value; the card simply refuses to vouch for it.

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

11. **A disclaimer ships with the card**, consistent with SPEC-14. Venue data is
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
- Drift guard green for `driver_card_shown`

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
- [ ] A sample of Lao script verified against an independent source, with the
      sample size, the result, and the resulting `source` values recorded
- [ ] Fare bands present for the three Laos regions
- [ ] Card works with the radio off, proven by a test that fails if any network
      call occurs
- [ ] Generated names never render as authoritative, with a test
- [ ] `driver_card_shown` in registry plus migration `0014`; drift guard green
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10); R1 grep clean
