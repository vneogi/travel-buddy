# Genie brief: SPEC-57 slice 1, Arrival Armor captain HUD

Read this whole file before touching anything. It is the complete job.
If something here is unclear, stop and ask; do not guess and do not
widen scope.

Start only when the planning agent (or owner) sends this brief with a
real base SHA.

Owning spec: `docs/specs/SPEC-57-arrival-armor.md`.
Parents: SPEC-12 (Driver Card), SPEC-49 (Show-to-driver), SPEC-10
(booking anchors as open trigger). This slice is Flutter-only. No
backend, no SQLite schema change, no migration, no Cloud Run deploy, no
new location permission, no brightness package (slice 1b), no fare
invention.

## 0. Context

Owner-accepted triage (2026-11-17): of the five moonshot ideas, only a
thin Arrival Armor is near-term. Geofence, BLE mesh, camera vision,
route deviation, and earbud whisper stay out. See VISION section 32.

Verified on `main` (re-verify in preflight):

1. Driver Card route: `/trip/:tripId/card/:nodeId` in
   `mobile/lib/routing/app_router.dart`. Opened from activity-card
   overflow `value: 'driver'` with
   `node.venueId ?? node.venueName` as the card id
   (`mobile/lib/widgets/activity_card.dart`).
2. `TripNode` has `nodeKind`, `bookingType`, `geoRegion`,
   `scheduledStart`, `venueId`, `venueName`, `isLocked`
   (`mobile/lib/data/models.dart`).
3. Booking types in the overflow / icons include `flight`, `hotel`,
   `train`, `tour`. There is no `ferry` type.
4. Regions for the December trip: `zanzibar_tanzania`,
   `nungwi_tanzania`.
5. `mobile/pubspec.yaml` assets currently list `assets/images/` only.
6. No `screen_brightness` / wakelock dependency. Do not add one.

## 1. Goal

1. Bundle `mobile/assets/arrival_hubs.json` with two seed hubs whose
   money and scam fields are null or empty (honest empty HUD).
2. Load and match a hub for a flight booking by `geo_region` +
   `booking_types` containing `flight`.
3. New captain screen: hub label, sourced fare block only when present,
   scam notes only when present, caption when any fare shows, button to
   open the next hotel Driver Card when one exists.
4. Overflow entry on flight bookings that match a hub.
5. Widget tests. Zero network calls on the new screen.

## 2. Preflight

1. `git fetch origin`. Work from the base SHA in the message that sent
   this brief.
2. Confirm section 0 items 1 to 6. If any differs, stop and report.
3. Confirm `origin/feat/spec57-arrival-armor` does not exist, and that
   `ArrivalArmor` / `arrival_hubs` do not already appear under
   `mobile/lib` or `mobile/assets`.
4. Branch: `feat/spec57-arrival-armor`.

## 3. Read before editing

- `docs/specs/SPEC-57-arrival-armor.md` (whole file)
- `docs/specs/SPEC-49-driver-handoff-and-tanzania-language.md`
- `docs/specs/SPEC-12-show-driver-cards.md` (offline + provenance)
- `docs/ENGINEERING_RULES.md` R14, R16, R17
- `mobile/lib/widgets/activity_card.dart` (overflow menu)
- `mobile/lib/routing/app_router.dart`
- `mobile/lib/data/models.dart` (`TripNode`)
- `mobile/lib/theme/typography.dart`, `colors.dart`, `spacing.dart`
- An existing Flutter widget test that seeds itinerary nodes (find with
  `rg activity_card` / `TripNode(` under `mobile/test/`)

## 4. Files you may touch

- `mobile/assets/arrival_hubs.json` (new)
- `mobile/pubspec.yaml` (add `assets/arrival_hubs.json` under `flutter:
  assets:` only; no new dependencies)
- `mobile/lib/features/arrival_armor/arrival_hubs.dart` (new: parse +
  match helpers)
- `mobile/lib/features/arrival_armor/arrival_armor_screen.dart` (new)
- `mobile/lib/routing/app_router.dart` (one route)
- `mobile/lib/widgets/activity_card.dart` (one overflow item + navigate)
- `mobile/lib/features/itinerary/itinerary_screen.dart` ONLY if the
  overflow needs the trip's node list to pick the next hotel; prefer
  passing a callback or the nodes list from the parent that already has
  them. Do not re-fetch.
- `mobile/test/spec57_arrival_armor_test.dart` (new)

Nothing else. No backend, no docs edits, no SPEC-49 Show-to-driver
changes, no brightness / SystemChrome brightness hacks, no new
packages.

## 5. Asset seed (exact)

Write `mobile/assets/arrival_hubs.json` as a single JSON object:

```json
{
  "hubs": [
    {
      "id": "znz_airport",
      "label": "Zanzibar Airport (ZNZ)",
      "geo_regions": ["zanzibar_tanzania", "nungwi_tanzania"],
      "booking_types": ["flight"],
      "currency": "TZS",
      "fare_band_low": null,
      "fare_band_high": null,
      "hard_ceiling": null,
      "official_option": null,
      "scam_notes": [],
      "surveyed_on": null,
      "source": null
    },
    {
      "id": "stone_town_ferry",
      "label": "Stone Town ferry terminal",
      "geo_regions": ["zanzibar_tanzania", "nungwi_tanzania"],
      "booking_types": ["train"],
      "currency": "TZS",
      "fare_band_low": null,
      "fare_band_high": null,
      "hard_ceiling": null,
      "official_option": null,
      "scam_notes": [],
      "surveyed_on": null,
      "source": null
    }
  ]
}
```

Do not fill money or scam fields with invented values. Owner data comes
later as a separate change.

## 6. Matching and next hotel

Pure functions in `arrival_hubs.dart`:

- `ArrivalHub` model matching the JSON fields (nullable nums as `int?`
  or `double?`; prefer `int?` for TZS whole shillings).
- `List<ArrivalHub> parseArrivalHubs(String json)`.
- `ArrivalHub? hubForBooking({required String? geoRegion, required
  String? bookingType, required List<ArrivalHub> hubs})`: first hub
  where `geoRegion` is in `geo_regions` and `bookingType` is in
  `booking_types`. Null geo or type -> null.
- `TripNode? nextHotelDestination({required TripNode from, required
  List<TripNode> nodes})`: among nodes with `nodeKind == 'booking'` and
  `bookingType == 'hotel'`, pick the earliest `scheduledStart` that is
  `>= from.scheduledStart`. If several share that start, prefer the one
  whose `geoRegion == from.geoRegion` when `from.geoRegion` is non-null.
  Otherwise earliest by start then stable by `nodeId`. Return null if
  none.

Load the asset once via `rootBundle.loadString('assets/arrival_hubs.json')`
on the screen (or a small provider). Cache in memory on the State; do
not hit the network.

## 7. Screen and copy

Route: `/trip/:tripId/arrival/:hubId` -> `ArrivalArmorScreen`.
Also accept the flight `nodeId` as an extra query or path segment if
you need it to compute the next hotel; simplest is to pass
`nodeId` as a path param:
`/trip/:tripId/arrival/:hubId/:nodeId` and look up the node from the
itinerary controller / cached trip already used by the itinerary
screen. If looking up the node requires a new network load, stop and
ask. Prefer: overflow handler receives the parent `List<TripNode>`,
computes `hub` + `nextHotel`, and pushes a route that carries
`hubId` plus optional hotel place ref
(`venueId ?? venueName`) as a query `?hotel=`.

Recommended push from overflow (exact keys):

- Menu value: `arrival_armor`
- Menu title exact: `Arrival armor`
- Show the menu item only when
  `node.nodeKind == 'booking' && hubForBooking(...) != null`
- On select: `context.push('/trip/$tripId/arrival/${hub.id}?hotel=$hotelRef')`
  where `hotelRef` is omitted when there is no next hotel
  (no trailing `?hotel=`).

Screen body, top to bottom:

1. AppBar title exact: `Arrival armor`. Back pops.
2. Hub `label` as the lead heading (`AppTypography.h1` or `display`).
3. Fare block, only if `fare_band_low` and `fare_band_high` are both
   non-null: heading `Fair fare guide`, body
   `{low} - {high} {currency}` and if `hard_ceiling != null` a second
   line `Walk-away above {ceiling} {currency}`. If
   `official_option` is a non-empty string, show it as its own line
   under the heading `Official option`. Under the fare block, caption
   exact: `Guides only -- confirm before you pay.` If `source` and
   `surveyed_on` are both non-null non-empty, one more caption line:
   `Source: {source} ({surveyed_on})`.
4. Scam block, only if `scam_notes` has at least one non-empty string:
   heading `Watch for`, then each note as a bullet. No notes -> omit
   the whole block.
5. When both fare and scam blocks are omitted, show one calm line
   exact: `No verified fare or tip sheet for this hub yet.`
6. Driver button, only when `hotel` query is present and non-empty:
   key `Key('arrival_open_driver_card')`, label exact:
   `Open driver card for hotel`, min height 48. Pushes
   `/trip/$tripId/card/$hotelRef`. When no hotel, omit the button
   (do not show a disabled control).

Rules:

- Zero Dio / http / Supabase calls from this screen.
- Do not change Driver Card or Show-to-driver UI.
- Do not call `SystemChrome` for brightness or orientation.
- Text wraps; no ellipsis that hides fare digits at 360dp width or
  2.0 text scale.
- Use existing `AppColors` / spacing tokens only.

## 8. Tests

`mobile/test/spec57_arrival_armor_test.dart`, exact names:

1. `hubForBooking matches flight in zanzibar_tanzania to znz_airport`
2. `hubForBooking returns null for hotel booking`
3. `hubForBooking returns null for unknown region`
4. `nextHotelDestination picks earliest hotel on or after flight`
5. `nextHotelDestination returns null when no hotel`
6. `screen omits fare and scam when asset fields are null`
7. `screen shows empty-hub calm line when no fare and no scam`
8. `screen shows Open driver card when hotel query set`
9. `screen omits Open driver card when hotel query absent`
10. `overflow offers Arrival armor for matching flight only`
    (pump a card with a flight node in a mapped region; expect the
    menu item; pump a hotel node; expect no menu item)

For JSON parse tests, embed the seed JSON as a string constant in the
test file (do not require rootBundle for pure helper tests). For the
screen tests, either inject a pre-parsed `ArrivalHub` or override the
loader; do not require network. Follow existing
`testWidgets` + MaterialApp + GoRouter patterns in sibling tests.

## 9. Stop and ask

Stop and ask (do not guess) if:

- Matching needs a backend field that does not exist on `TripNode`.
- Opening the Driver Card requires a place ref you cannot get from the
  hotel node.
- You believe a brightness package is required for slice 1 (it is not;
  that is slice 1b).
- Any existing test fails for a reason outside this slice.
- The overflow parent cannot supply `List<TripNode>` without a wide
  refactor.

## 10. Done when

- `dart analyze` clean on touched files (infos pre-existing elsewhere
  are fine).
- `flutter test mobile/test/spec57_arrival_armor_test.dart` green.
- Full `flutter test` green on the branch.
- Push `feat/spec57-arrival-armor` and report the SHA plus a short
  note of any stop-and-ask decisions taken.

Do not open the PR; the planning agent reviews and opens it.
