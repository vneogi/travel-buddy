# Genie Brief -- SPEC-12 Show Driver Cards (Offline)

> Status: READY TO IMPLEMENT. Paste this entire file to Genie Code.
> Land via PR to main, not direct push. Owner has no laptop -- unit and
> widget tests + flutter analyze in CI.

Canonical spec: `docs/specs/SPEC-12-show-driver-cards.md`
Render contract: `docs/specs/SPEC-22-render-contract.md` (uses `FactView`, `FactEnvelope`, `ConfirmAffordance`)
Offline storage: `docs/specs/SPEC-02-offline-queue-and-sync.md` (`cache_place` in `OfflineDatabase`)
Signals registry: `docs/specs/SPEC-06-behavioral-signals.md` (R5: one registry, one source of truth)

## Goal

A full-screen, high-contrast card the traveller shows a driver: venue name
in large native script (Lao, Arabic, etc.), nearest landmark (in native
script for the driver and English for the traveller), coordinates, and a
fair-fare band.

Must work **100% offline** with zero network calls, reading entirely from
SQLite `cache_place`.

When a local name is `generated` (unverified), it renders via SPEC-22
`FactView` in `FactTier.ask` with `ConfirmAffordance` (*"Does the sign say this?"*):
- Tapping **Confirm** emits `name_confirmed` with `verdict: 'confirmed'`,
  updates local cache to `source: 'field_verified'`, and promotes the card
  to `FactTier.assert_`.
- Tapping **Dismiss / Reject** emits `name_confirmed` with `verdict: 'rejected'`
  and degrades the card locally without deleting server data.
- When opening the card, emits `driver_card_shown` with `was_offline` and `name_source`.

## Deliverables in this PR

1. `models/signal_types.py` -- Register `driver_card_shown` and `name_confirmed`.
2. `supabase/migrations/0020_driver_card_signals.sql` -- Seed both signal types.
3. `models/schemas.py` & `agents/state_machine.py` -- Ensure `TripNode` carries
   `names_local`, `landmarks_local`, and `nearest_landmark`.
4. `mobile/lib/data/models.dart` -- Add `namesLocal`, `landmarksLocal`,
   `nearestLandmark` to Dart `TripNode`.
5. `mobile/lib/services/signal_service.dart` -- Add `emitDriverCardShown` and
   `emitNameConfirmed`.
6. `mobile/lib/features/driver_card/driver_card_helpers.dart` -- Region-based
   language selection, fair fare resolution, place cache serializer/deserializer.
7. `mobile/lib/features/driver_card/driver_card_screen.dart` -- Full-screen,
   high-contrast view with `FactView`, coordinates, landmarks, fare band,
   screenshot affordance, and disclaimer.
8. `mobile/lib/widgets/activity_card.dart` -- Driver card icon affordance on cards.
9. `mobile/lib/routing/app_router.dart` -- Route `/trip/:tripId/card/:nodeId` or
   `/card/:placeRef`.
10. `mobile/lib/features/itinerary/itinerary_notifier.dart` -- Pre-cache place data
    into SQLite `cache_place` when trips/nodes load.
11. Unit & Widget tests under `mobile/test/features/driver_card/` proving offline
    rendering, tier mapping, signal emission, and sabotage proofs.

---

## 1. Signals & Schema (Python + SQL)

### `models/signal_types.py`

Add to `SIGNAL_TYPES`:
```python
    "driver_card_shown": "json",
    "name_confirmed": "json",
```

Add to `PAYLOAD_SHAPES`:
```python
    "driver_card_shown": "json: {place_ref: str, was_offline: bool, name_source: str}",
    "name_confirmed": "json: {place_ref: str, lang: str, shown_value: str, verdict: str} -- verdict is confirmed or rejected",
```

### `supabase/migrations/0020_driver_card_signals.sql`

```sql
-- =============================================================================
-- Migration: 0020_driver_card_signals.sql
-- Description: Register driver_card_shown and name_confirmed signal types
--              (SPEC-12 decisions 10 and 11).
-- Depends on: 0002_signals_core.sql (signal_type table)
-- =============================================================================

INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('driver_card_shown', 'behavioral', 'json', NULL, 'none',
     'Traveller opened a driver card for a venue (offline or online)'),
    ('name_confirmed', 'explicit_user', 'json', NULL, 'none',
     'Traveller verified or rejected local-script venue signage (verdict=confirmed|rejected)')
ON CONFLICT (key) DO NOTHING;
```

### `models/schemas.py` & `agents/state_machine.py`

In `models/schemas.py`, add optional fields to `TripNode`:
```python
    names_local: Optional[Dict[str, Any]] = None
    landmarks_local: Optional[Dict[str, Any]] = None
    nearest_landmark: Optional[str] = None
```

In `agents/state_machine.py` `_node_from_venue`:
```python
    names_local=getattr(venue, "names_local", None),
    landmarks_local=getattr(venue, "landmarks_local", None),
    nearest_landmark=getattr(venue, "nearest_landmark", None),
```

---

## 2. Dart Models & Signal Service

### `mobile/lib/data/models.dart`

Add to `TripNode`:
```dart
  final Map<String, dynamic>? namesLocal;
  final Map<String, dynamic>? landmarksLocal;
  final String? nearestLandmark;
```
Update constructor, `fromJson`, and `toJson` (if present) to parse:
- `names_local` -> `namesLocal`
- `landmarks_local` -> `landmarksLocal`
- `nearest_landmark` -> `nearestLandmark`

### `mobile/lib/services/signal_service.dart`

Add typed helpers:
```dart
  Future<void> emitDriverCardShown({
    required String placeRef,
    required bool wasOffline,
    required String nameSource,
    String? tripId,
  }) =>
      emit(
        signalType: 'driver_card_shown',
        placeRef: placeRef,
        tripId: tripId,
        valueJson: {
          'place_ref': placeRef,
          'was_offline': wasOffline,
          'name_source': nameSource,
        },
      );

  Future<void> emitNameConfirmed({
    required String placeRef,
    required String lang,
    required String shownValue,
    required String verdict,
    String? tripId,
  }) {
    assert(verdict == 'confirmed' || verdict == 'rejected', 'Invalid verdict: $verdict');
    return emit(
      signalType: 'name_confirmed',
      placeRef: placeRef,
      tripId: tripId,
      valueJson: {
        'place_ref': placeRef,
        'lang': lang,
        'shown_value': shownValue,
        'verdict': verdict,
      },
    );
  }
```

---

## 3. Driver Card Logic & Helpers

Create `mobile/lib/features/driver_card/driver_card_helpers.dart`:

### Language Resolution (SPEC-12 Decision 4)
Ordered preference list per region (interim until SPEC-13):
- Laos (`luang_prabang_laos`, `vang_vieng_laos`, `vientiane_laos`, or region containing `laos`): `['lo', 'th', 'en']`
- Dubai (`dubai_uae` or region containing `dubai`): `['ar', 'en']`
- Default fallback: `['en']`

Helper:
```dart
MapEntry<String, Map<String, dynamic>>? resolvePreferredLocalEntry({
  required Map<String, dynamic>? localizedMap,
  required String? geoRegion,
})
```
Walks the ordered language list for the region, returns the first matching
entry where `value` is a non-empty string.

### Provenance to FactTier Mapping (SPEC-12 Decision 3 & SPEC-22)
```dart
FactTier tierForNameSource(String source) {
  switch (source) {
    case 'wikidata':
    case 'osm':
    case 'official':
    case 'manual':
    case 'field_verified':
      return FactTier.assert_;
    case 'generated':
      return FactTier.ask;
    default:
      return FactTier.refuse;
  }
}
```

### Fair Fare Band (SPEC-12 Decision 6)
```dart
String resolveFairFareBand(String? geoRegion) {
  final region = (geoRegion ?? '').toLowerCase();
  if (region.contains('laos')) {
    return '20,000 - 50,000 LAK (Tuk-tuk / Loca)';
  } else if (region.contains('dubai')) {
    return '20 - 40 AED (Meter taxi short trip)';
  }
  return 'Standard meter / local fare';
}
```

### Place Cache Serialization
```dart
class PlaceDriverCardData {
  final String placeRef;
  final String venueName;
  final Map<String, dynamic>? namesLocal;
  final String? nearestLandmark;
  final Map<String, dynamic>? landmarksLocal;
  final double? lat;
  final double? lng;
  final String? microLocation;
  final String? geoRegion;

  // fromJson, toJson, and factory from TripNode
}
```

---

## 4. SQLite Pre-caching on Trip Load

In `mobile/lib/features/itinerary/itinerary_notifier.dart`:
When `ItineraryController.load()` receives `trip.nodes` (or `applyEvent` receives `result.updatedNodes`):
Iterate nodes and call `offlineDb.cachePlace(placeRef, jsonEncode(placeData))` so all nodes in the trip are guaranteed to be in SQLite `cache_place`.

---

## 5. UI: Full-Screen Driver Card

Create `mobile/lib/features/driver_card/driver_card_screen.dart`:

### UI Requirements (SPEC-12 Decisions 3, 7, 8, 9, 12)
- **High Contrast & Sunlight-Readable:**
  - Clean card surface (`AppColors.card` / high-contrast ink).
  - Prominent back / close button in AppBar or top right.
- **Headline (Native Script):**
  - Uses `FactView` with `FactEnvelope`:
    - `tier`: `tierForNameSource(source)`
    - `value`: Native script text (e.g. Lao: "\u0ea7\u0eb1\u0e94\u0e8a\u0ebd\u0e87\u0e97\u0ead\u0e87")
    - `source`: e.g. `wikidata` or `generated`
  - Style: Huge, readable at arm's length (e.g. 32-40pt text inside FactView / headline).
  - If `FactTier.ask` (generated):
    - `FactView` automatically renders `ConfirmAffordance` (*"Is this still correct? [Confirm] [X]"*).
    - Tapping **Confirm**:
      - Emits `name_confirmed` signal (`verdict: 'confirmed'`).
      - Updates SQLite `cache_place` record so `source` becomes `'field_verified'`.
      - Updates widget state to display as verified (`FactTier.assert_`).
    - Tapping **Dismiss / Reject**:
      - Emits `name_confirmed` signal (`verdict: 'rejected'`).
      - Degrades the card display locally to explicit degradation (`FactTier.refuse`).
  - If no native script available or rejected:
    - Renders `FactTier.refuse` (*"Information not available"* / *"Local name not available"*), alongside Roman name and coordinates. Never an empty box!
- **Landmark Section:**
  - Native script landmark (`landmarks_local`) if available: displayed prominently for the driver.
  - English landmark (`nearest_landmark` / `microLocation`) displayed for the traveller.
- **Roman Name & Coordinates:**
  - Venue Roman name (e.g. "Wat Xieng Thong").
  - Formatted Coordinates: `19.89758, 102.14321`.
- **Fair Fare Band:**
  - Displayed in a clear badge / card: e.g. `Fair Fare: 20,000 - 50,000 LAK (Tuk-tuk / Loca)`.
- **Screenshot & Offline Durability Affordance (Decision 9):**
  - Button or banner: *"Screenshot this card for offline safety"*.
- **Disclaimer (Decision 12):**
  - Caption at bottom: *"Venue and fare information is an offline travel aid."*
- **Signal on Open (Decision 10):**
  - In `initState` / controller load: emits `driver_card_shown` with `{place_ref, was_offline, name_source}`.

### Entry Points
1. In `mobile/lib/widgets/activity_card.dart`:
   - Add a driver card button (e.g. `Icon(Icons.directions_car_outlined, size: 20)`, tooltip `'Show driver card'`).
   - Tapping navigates to `/trip/:tripId/card/:nodeId` (or pushes `DriverCardScreen`).
2. In `mobile/lib/routing/app_router.dart`:
   - Add route:
     ```dart
     GoRoute(
       path: '/trip/:tripId/card/:nodeId',
       builder: (context, state) => DriverCardScreen(
         tripId: state.pathParameters['tripId']!,
         nodeId: state.pathParameters['nodeId']!,
       ),
     ),
     ```

---

## 6. Tests & Sabotage Proofs (R17)

Create `mobile/test/features/driver_card/driver_card_test.dart`:

### Required Tests

1. **`verified name renders assert tier headline`**:
   - Given a place with `source: 'wikidata'` and Lao script name.
   - FactEnvelope has `tier: FactTier.assert_`.
   - Card displays Lao name in assert styling without unconfirmed warning.

2. **`generated name renders ask tier with confirm affordance`**:
   - Given a place with `source: 'generated'` and Lao script name.
   - FactEnvelope has `tier: FactTier.ask`.
   - Card displays `ConfirmAffordance` with confirm button.

3. **`confirming promotes source to field_verified and emits signal`**:
   - Tap Confirm on unconfirmed card.
   - Signal `name_confirmed` is enqueued in outbox with `verdict: 'confirmed'`.
   - Cached place row in SQLite `cache_place` is updated to `source: 'field_verified'`.
   - UI state promotes to assert tier.

4. **`rejecting emits name_confirmed rejected and degrades locally`**:
   - Tap Dismiss/Reject on unconfirmed card.
   - Signal `name_confirmed` is enqueued in outbox with `verdict: 'rejected'`.
   - UI degrades to explicit refuse / degraded view.

5. **`driver_card_shown emitted on card open with offline status`**:
   - Opening the card enqueues `driver_card_shown` with `was_offline` boolean and `name_source`.

6. **`driver card renders strictly from SQLite cache with network disabled`**:
   - Configure a mock `ApiClient` that throws `NetworkException` on ANY call.
   - Populate SQLite `cache_place`.
   - Driver card loads and renders successfully with zero network errors.

7. **`language selection walks region priority list`**:
   - Laos region with `th` and `en` (no `lo`) falls back to `th`.
   - Dubai region with `ar` and `en` chooses `ar`.

8. **`missing local name produces explicit refuse degradation, never blank`**:
   - Place with null `names_local` renders explicit degradation text and Roman name + coordinates.

### Sabotage Proofs (Name these specifically in PR)
- **Sabotage 1:** Change `tierForNameSource` so `'generated'` returns `FactTier.assert_`.
  - Named test `generated name renders ask tier with confirm affordance` must FAIL.
- **Sabotage 2:** Force a network call inside `DriverCardScreen` load.
  - Named test `driver card renders strictly from SQLite cache with network disabled` must FAIL.
- **Sabotage 3:** Change `resolveFairFareBand` to return empty string for Laos.
  - Named test for fare band must FAIL.
- **Sabotage 4:** Invert confirm verdict to `'rejected'` in confirm handler.
  - Named test `confirming promotes source to field_verified and emits signal` must FAIL.

---

## 7. Python Drift Guard Check

Run backend test suite:
`pytest tests/test_signal_types.py -v`
Must be green (`driver_card_shown` and `name_confirmed` in both `signal_types.py` and `0020_driver_card_signals.sql`).

---

## Proof Checklist before PR

- `grep -rn '\\$' mobile/lib` -- only upgrade_screen price strings (R1)
- `flutter analyze --no-fatal-infos` -- 0 errors, 0 warnings
- `flutter test` -- all unit and widget tests pass
- Python: `pytest -q -ra` clean, `ruff check .` clean
- All living docs and comments pure ASCII (R14)

## PR Details

- Branch: `feat/spec-12-driver-card`
- Title: `feat(mobile): SPEC-12 offline driver card, local script verification, signals`
- Body: Summary of 11 deliverables, verification evidence, sabotage proofs.
