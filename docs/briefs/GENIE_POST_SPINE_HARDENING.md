# Genie Brief -- Post-Spine Hardening (geoRegion, authHalted, Hotel Matching)

> Status: READY TO IMPLEMENT. Paste this entire file to Genie Code.
> Land via PR to main, not direct push. Owner has no laptop -- unit and
> widget tests + flutter analyze in CI.

Canonical specs: `docs/specs/SPEC-12-show-driver-cards.md`, `docs/specs/SPEC-02-offline-queue-and-sync.md`, `docs/specs/SPEC-04-offline-vault.md`
Rules: `docs/ENGINEERING_RULES.md` (R1, R3, R14, R16, R17)

## Goal

Fix 3 specific data-layer and offline issues discovered during spine verification:

1. **`geoRegion` in Dart `TripNode` & `PlaceDriverCardData`:**
   Add `geoRegion` to Dart `TripNode` (`geo_region` in JSON). Thread it through `PlaceDriverCardData.fromTripNode(node)`. Ensure `/trip/create` in Python also stamps `geo_region` on seeded nodes.
2. **`_authHalted` Clearance & Visibility:**
   Expose `authHalted` on `SyncStatusScreen` with an explicit status indicator. Add `resetAuthHalted()` on `SyncEngine` and trigger it when the user taps refresh or manually triggers sync.
3. **Robust Hotel Matching:**
   Ensure `findHotelNode` tests against real venue names from the dataset (e.g., "Villa Maly", "Amantaka") and relies cleanly on `bookingType == 'hotel'` or `nodeKind == 'hotel'`.
4. **`PlaceDriverCardData.fromJson` Cast Safety:**
   Use `(j['names_local'] as Map?)?.cast<String, dynamic>()` and `(j['landmarks_local'] as Map?)?.cast<String, dynamic>()` for runtime safety.

---

## 1. `geoRegion` Threading (Dart & Python)

### `mobile/lib/data/models.dart`
Add `final String? geoRegion;` to `TripNode`:
- Constructor parameter `this.geoRegion,`
- `TripNode.fromJson`: `geoRegion: j['geo_region'] as String?,`
- `TripNode.toJson`: `'geo_region': geoRegion,`

### `mobile/lib/features/driver_card/driver_card_helpers.dart`
In `PlaceDriverCardData.fromTripNode`:
Change:
```dart
  factory PlaceDriverCardData.fromTripNode(TripNode node) {
    return PlaceDriverCardData(
      placeRef: node.venueId ?? node.venueName,
      venueName: node.venueName,
      namesLocal: node.namesLocal,
      nearestLandmark: node.nearestLandmark,
      landmarksLocal: node.landmarksLocal,
      lat: node.lat,
      lng: node.lng,
      microLocation: node.microLocation,
      geoRegion: node.geoRegion, // Thread from TripNode!
    );
  }
```

In `PlaceDriverCardData.fromJson`:
Change map casts:
```dart
  factory PlaceDriverCardData.fromJson(Map<String, dynamic> j) {
    return PlaceDriverCardData(
      placeRef: j['place_ref'] as String,
      venueName: j['venue_name'] as String,
      namesLocal: (j['names_local'] as Map?)?.cast<String, dynamic>(),
      nearestLandmark: j['nearest_landmark'] as String?,
      landmarksLocal: (j['landmarks_local'] as Map?)?.cast<String, dynamic>(),
      lat: (j['lat'] as num?)?.toDouble(),
      lng: (j['lng'] as num?)?.toDouble(),
      microLocation: j['micro_location'] as String?,
      geoRegion: j['geo_region'] as String?,
    );
  }
```

### `routers/trip_router.py`
In `create_trip`, stamp `geo_region=settings.geo_fence` on each seeded `TripNode` in `nodes = [...]` so newly created demo trip nodes carry the region.

---

## 2. `_authHalted` Visibility & Clearance

### `mobile/lib/offline/sync_engine.dart`
Add `resetAuthHalted()` method:
```dart
  /// Clears the auth halted state (called on user refresh / re-auth).
  void resetAuthHalted() {
    _authHalted = false;
  }
```

In `SyncStatusScreen` (`mobile/lib/features/debug/sync_status_screen.dart`):
- When user taps refresh button in AppBar, call `ref.read(syncEngineProvider).resetAuthHalted();` and `ref.read(syncEngineProvider).syncOnce();`.
- In `_buildStatusCard` / top card list: if `syncEngine.authHalted`, display a warning card:
  `_StatusCard(title: 'Auth Status', status: 'HALTED (401)', color: Colors.red)`

---

## 3. Hotel Matching & Parser Tests

### `mobile/lib/features/rescue/hotel_rescue_sheet.dart`
Update `findHotelNode`:
```dart
TripNode? findHotelNode(List<TripNode> nodes) {
  return nodes.where((n) {
    if (n.bookingType == 'hotel' || n.nodeKind == 'hotel') return true;
    if (n.nodeKind == 'booking' && n.bookingType == 'hotel') return true;
    final name = n.venueName.toLowerCase();
    return name.contains('hotel') ||
        name.contains('resort') ||
        name.contains('hostel') ||
        name.contains('villa') ||
        name.contains('guesthouse');
  }).firstOrNull;
}
```

---

## 4. Tests & Sabotage Proofs (R17)

### `mobile/test/features/driver_card/driver_card_test.dart`
Add end-to-end sabotage test for `geoRegion`:
```dart
    test('TripNode with geo_region luang_prabang_laos resolves Lao script and LAK fare via fromTripNode', () {
      final node = TripNode.fromJson({
        'node_id': 'n1',
        'venue_name': 'Wat Xieng Thong',
        'geo_region': 'luang_prabang_laos',
        'names_local': {
          'lo': {'value': 'Lao Name', 'source': 'wikidata'},
          'en': {'value': 'English Name', 'source': 'wikidata'},
        },
      });
      final placeData = PlaceDriverCardData.fromTripNode(node);
      expect(placeData.geoRegion, equals('luang_prabang_laos'));

      final entry = resolvePreferredLocalEntry(
        localizedMap: placeData.namesLocal,
        geoRegion: placeData.geoRegion,
      );
      expect(entry, isNotNull);
      expect(entry!.key, equals('lo'));
      expect(entry.value['value'], equals('Lao Name'));

      final fare = resolveFairFareBand(placeData.geoRegion);
      expect(fare, contains('LAK'));
    });
```

### `mobile/test/features/rescue/hotel_rescue_test.dart`
Add test for non-"hotel" named accommodation:
```dart
    test('identifies hotel booking with non-generic name (e.g. Villa Maly)', () {
      final nodes = [
        _node('Villa Maly', nodeKind: 'booking', bookingType: 'hotel'),
        _node('Night Market'),
      ];
      final hotel = findHotelNode(nodes);
      expect(hotel, isNotNull);
      expect(hotel!.venueName, equals('Villa Maly'));
    });
```

### `mobile/test/offline_sync_test.dart`
Add test for `resetAuthHalted`:
```dart
  test('resetAuthHalted clears halted state allowing sync to retry', () async {
    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(const UnauthorizedException());

    await syncEngine.syncOnce();
    expect(syncEngine.authHalted, isTrue);

    // resetAuthHalted clears it
    syncEngine.resetAuthHalted();
    expect(syncEngine.authHalted, isFalse);
  });
```

---

## Proof Checklist before PR

- `grep -rn '\\$' mobile/lib` -- clean (only `upgrade_screen` price strings) (R1)
- `flutter analyze --no-fatal-infos` -- 0 errors, 0 warnings
- `flutter test` -- all unit & widget tests pass
- Python: `pytest -q -ra` -- 0 failures, `ruff check .` clean
- Pure ASCII in all docs and comments (R14)

## PR Details

- Branch: `fix/post-spine-hardening`
- Title: `fix(mobile): geoRegion threading for driver card, authHalted reset, hotel matching`
- Body: Summary of fixes, verification evidence, sabotage proofs.
