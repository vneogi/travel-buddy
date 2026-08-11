# SPEC-12: Show Driver Cards (Offline)

> Status: SPECIFIED. Not implemented, and blocked on data that does not exist.
>
> Migration numbering: the column additions below are migration `0011`, shared
> with the schema-drift fix. `driver_card_shown` is `0014`, after 0012 (booking
> anchors) and 0013 (preference_choice).

## Goal

A full-screen card the traveller shows a driver: venue name in large native
script, nearest landmark, coordinates, and a fair-fare band. Fully functional
with the radio off. This is VISION section 26, and the concrete form of
capability 7 in section 11.

## Blocking finding: the data does not exist yet

`venues_rag` has no `name_local` column and no `nearest_landmark` column.
Confirmed against migrations `0001` and `0008`, and against the `upsert_venues`
field list in `scripts/load_venues.py`, which writes neither. None of the 58
Laos venues carries Lao script. Only `venue_dish` has `name_local`, and that is
for dishes.

This is rule R9 exactly: the schema cannot express the fact, so nothing errors
to tell you the card is impossible. **Do not start the UI first.** The order is
migration, then loader, then curation, then UI.

Curation is the critical path, because it is the only part an agent cannot do:
58 venues need a Lao-script name and a driver-recognisable landmark, sourced
from Google Maps. That is manual data entry on the JSON files, it needs no
laptop toolchain, and it should start immediately in parallel with everything
else.

## Design decisions

1. **Migration `0011` adds `name_local TEXT NULL` and `nearest_landmark TEXT
   NULL` to `venues_rag`**, additive and nullable. Fold in
   `typical_dwell_minutes`, `indoor_outdoor` and `price_band` in the same
   migration, since the loader already writes those three but no migration
   declares them -- the live schema and the migration set have diverged.

2. **Fare bands are per-region, not per-venue.** Extend `config/regions.py` with
   a typical fare band and per-km rate per region. Curating one fare table per
   city is tractable; curating a fare per venue is not, and it would be stale by
   October anyway.

3. **The card renders entirely from the offline cache.** It reads the
   `cache_place` table that SPEC-02 already created. When a trip loads,
   pre-cache `name_local`, `nearest_landmark` and coordinates for every node. If
   the card needs a network call it has failed at its only job.

4. **Degrade explicitly, never blankly.** When `name_local` is null, the card
   states that no local-script name is available and shows the roman name plus
   coordinates, rather than rendering an empty box. This is rule R6 applied to
   data rather than credentials: a visible degradation beats a silent one.

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
- Loader round-trips `name_local` and `nearest_landmark`, including the null case
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

- [ ] Migration `0011` adds `name_local`, `nearest_landmark`, and the three
      undeclared columns; additive-only proven by grep
- [ ] `scripts/load_venues.py` writes all five, with a test on the null path
- [ ] All 58 Laos venues have `name_local`; count query proves zero nulls in the
      three Laos regions
- [ ] Fare bands present for the three Laos regions in `config/regions.py`
- [ ] Card works with the radio off, proven by a test that fails if any network
      call occurs
- [ ] Null `name_local` degrades explicitly, with a test
- [ ] `driver_card_shown` in registry plus migration `0014`; drift guard green
- [ ] Suite green with skip reasons named (R8); verified from `origin/main`
      (R10); R1 grep clean
