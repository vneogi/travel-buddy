# Genie Brief: SPEC-42 -- remove catalog-derived date caps

Start a new branch from current `origin/main` (`b7dac5e` or later):

```text
feat/spec42-uncap-trip-span
```

Do not merge. Do not deploy. Do not build an APK.
Do not start from dirty local `feat/spec41-reachability`.
Do not implement hotel lat/lng, dual check-in/out cards, named slots,
`pack_day` booking wiring, empty-day Add/Move, place-detail, paste, or Ask.

Read first:

- `docs/briefs/GENIE_REMAINDERS_SEQUENCE.md`
- `docs/specs/SPEC-42-flexible-trip-span.md` (No catalog-derived date cap;
  At most five generated starter days; Empty days are first-class;
  API evolution JSON example)
- `docs/AWAITING_VERIFICATION.md` (Sep 18 old-APK date-cap finding)
- `docs/ENGINEERING_RULES.md` (R1 Dart `\$`, R17)
- `docs/WAYS_OF_WORKING.md`
- `routers/trip_router.py` (create `over_capacity`, options
  `max_days_by_region`)
- `services/catalog_itinerary.py` (`range_nodes_from_catalog`,
  `compute_max_days_for_region`)
- `services/corridor_itinerary.py` (segment `max_days`)
- `mobile/lib/features/create_trip/create_trip_screen.dart`
  (`Up to $maxDays days`, snackbar Maximum N days)
- `mobile/lib/widgets/corridor_date_form.dart`
- `tests/test_spec40_guided_create.py`
- `mobile/test/spec40_create_wizard_test.dart`

Do not edit this brief.

## Why this slice exists

Sep 18 old APK: destination cards and the date picker showed catalog
limits such as "Up to 2 days" and "Maximum 2 days for this destination."
The owner could not enter the trip they are taking.

Current main still does that:

- create options advertise `max_days_by_region` from
  `compute_max_days_for_region`
- `trip_router` rejects `num_days > max_days` as `over_capacity`
- Flutter destination tiles say `Up to $maxDays days` and refuse a
  longer picker range
- corridor create uses `corridor.max_days_for_region`

SPEC-42 already decided: trip span and auto-fill capacity are different
fields. Catalog fill is not a user-facing maximum.

Uncapping the UI without changing create is not enough: a 10-day post
still dies in `range_nodes_from_catalog`, which packs every calendar
day at `VENUES_PER_DAY` and raises `InsufficientCatalog`.

## Goal

After this slice:

1. Destination list and date picker do not show, disable, or reject
   using catalog `max_days`. No "Up to N days" / "Maximum N days for
   this destination" copy.
2. Create accepts a span longer than catalog-packable days. Inclusive
   `creation_context` start/end stay the posted local dates.
3. Initial generation populates
   `min(5, trip_calendar_days, feasible_content_days)` days, not every
   calendar day. First and last day are included when at least two days
   can be populated. Intermediate populated days spread evenly.
4. Dates with no nodes still exist as empty days in the itinerary UI
   (SPEC-31 date headers). Empty is not an error. Optional short copy
   that the day is open. No Add/Move in this slice.
5. A high API safety bound of 90 inclusive days rejects abusive or
   accidental multi-year payloads (`trip_span_sanity_days`). It is not
   computed from venues and is not shown as destination advice.
6. Options advertise decoupled fields, for example
   `max_auto_populated_days` (5) and `trip_span_sanity_days` (90).
   Do not keep one field that means both span and fill. Old
   `max_days_by_region` may remain as an informational catalog-capacity
   hint for tests that still assert it exists, but create and the
   Flutter wizard must not use it as a user-facing cap.
7. Corridor create follows the same product rule per city and for
   total corridor days: no catalog/corridor table cap in the UI or as
   the create rejection. Still apply the 90-day sanity bound per
   segment and on the inclusive corridor span.

## Required proofs

Python:

- create a single-city trip whose calendar span exceeds advertised
  catalog `max_days` for that region; 201, not 422 `over_capacity`;
  `creation_context` start/end match the post; populated node-days
  <= 5 and <= feasible content
- a 10-day span with enough catalog for two packable days creates
  those two days plus empty dates in the span, no fabricated filler
- 91 inclusive days returns 422 with a sanity error code, not
  `over_capacity` and not a catalog N
- first+last populated when populated_day_count >= 2
- existing advertised-max create tests still pass for spans that
  already fitted

Flutter:

- destination tile has no "Up to N days"
- picking a range longer than old catalog maxDays does not snackbar
  "Maximum N days for this destination"
- wizard review or itinerary shows empty dates in the span
- `grep -rn '\\$' mobile/lib` still only the two price strings in
  `upgrade_screen.dart`

## Explicitly out

- Empty-day Add activity / Move between days (rest of SPEC-42)
- Named slots (brief 3)
- Hotel coords / dual timestamps (brief 2)
- Changing `violates_hotel_return` missing-coord behavior
- Deploy, APK, SPEC-25, SPEC-43/44
- Inventing venues to fill empty days

## Done when

`pytest -q` and the touched Flutter tests are green on the branch.
Do not merge. Planning reviews, then the owner may laptop-run.
