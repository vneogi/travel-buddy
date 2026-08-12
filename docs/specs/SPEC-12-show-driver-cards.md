# SPEC-12: Show Driver Cards (Offline)

> Status: SPECIFIED. Not implemented. Not blocked on curation -- see the
> corrected finding below.
>
> Migration numbering: the column additions below are migration `0011`, shared
> with the schema-drift fix. `driver_card_shown` is `0014`, after 0012 (booking
> anchors) and 0013 (preference_choice).

## Goal

A full-screen card the traveller shows a driver: venue name in large native
script, nearest landmark, coordinates, and a fair-fare band. Fully functional
with the radio off. This is VISION section 26, and the concrete form of
capability 7 in section 11.

## Corrected finding: the data exists, the loader discards it

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

What is actually broken is the loader. `scripts/load_venues.py` writes none of
these keys to `venues_rag`, and it ignores any JSON key outside its write set
without comment. `micro_location` and `wheelchair_notes` are discarded the same
way. Five curated fields per venue are lost on every load, and nothing errors.

This is rule R9 in a sharper form than the rule currently states. The schema
could not express the fact, and rather than failing, the loader behaved exactly
as though the fact had never been provided. A missing column at least breaks a
write; a silently ignored key produces a successful load and a quietly poorer
product.

The order is therefore migration, then loader, then UI. Curation is done. The
remaining human task is verification: spot-check a sample of the Lao script
against OpenStreetMap `name:lo` tags or Lao-language map listings. Temples and
landmarks are low risk. Small restaurants and tour operators are where a
generated transliteration can masquerade as a real Lao name, and a plausible
wrong name shown to a driver is worse than an honest English fallback.

## Design decisions

1. **Migration `0011` carries the columns.** As committed it adds `name_local`,
   `nearest_landmark`, `typical_dwell_minutes`, `indoor_outdoor` and
   `price_band`, all additive and nullable. It is unapplied, so it is amended
   rather than superseded, to add `nearest_landmark_local`, `micro_location` and
   `wheelchair_notes`. The last of those is the only real evidence behind the
   `mobility_limited` audience filter, which is recorded elsewhere as too loose
   to be useful -- it has never had data to be useful with.

2. **Fare bands are per-region, not per-venue.** Extend `config/regions.py` with
   a typical fare band and per-km rate per region. Curating one fare table per
   city is tractable; curating a fare per venue is not, and it would be stale by
   October anyway.

3. **The card renders entirely from the offline cache.** It reads the
   `cache_place` table that SPEC-02 already created. When a trip loads,
   pre-cache `name_local`, `nearest_landmark`, `nearest_landmark_local` and
   coordinates for every node. If the card needs a network call it has failed at
   its only job.

4. **Degrade explicitly, never blankly.** When `name_local` is null, the card
   states that no local-script name is available and shows the roman name plus
   coordinates, rather than rendering an empty box. This is rule R6 applied to
   data rather than credentials: a visible degradation beats a silent one. The
   loader defect above is the same principle violated one layer down.

5. **Optimise for a stranger reading it at arm's length in sunlight.** Maximum
   type size, maximum contrast, no app chrome. Include an explicit "screenshot
   this" affordance, because a screenshot survives a dead app, a dead battery
   saver mode, and a crash -- the failure modes that matter when stranded.

6. **New signal type `driver_card_shown`**, client-emittable, `value_json` of
   `{place_ref, was_offline}`. This is the only way to learn whether the Vault
   is actually used, which is the bet in section 11 capability 7. It queues
   offline and syncs later, which is also a neat proof that offline capture
   works. Registry plus migration `0014` in the same commit (R5).

## Tests

- Migration `0011` is additive only: no `DROP`, no `RENAME`, no type change.
  Grep the file to prove it.
- No curated JSON key is silently dropped. The loader either writes a key or
  declares it ignored in an explicit set; a key present in the data files and in
  neither set fails the test. This is the defect above, turned into a guard.
- Loader round-trips `name_local`, `nearest_landmark` and
  `nearest_landmark_local`, including the null case
- Card renders from the SQLite cache with the API client stubbed to throw on any
  call -- this is the test that proves offline, per R7, and it must fail if a
  network call is introduced
- Null `name_local` produces the explicit degraded card, asserted on rendered
  text
- `driver_card_shown` persists to the outbox while offline and syncs on
  reconnect
- Fare band resolves per region, with a named fallback for unregistered regions
- Drift guard green for `driver_card_shown`

## Acceptance

- [ ] Migration `0011` amended with `nearest_landmark_local`, `micro_location`
      and `wheelchair_notes`; additive-only proven by grep
- [ ] `scripts/load_venues.py` writes every curated field, with a test on the
      null path and a guard against silently dropped keys
- [ ] A count query proves zero `name_local` nulls across the three Laos regions
      after a re-load
- [ ] A sample of Lao script verified against an independent source, with the
      sample size and result recorded
- [ ] Fare bands present for the three Laos regions in `config/regions.py`
- [ ] Card works with the radio off, proven by a test that fails if any network
      call occurs
- [ ] Null `name_local` degrades explicitly, with a test
- [ ] `driver_card_shown` in registry plus migration `0014`; drift guard green
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10); R1 grep clean
