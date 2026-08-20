# Genie Brief -- SPEC-04 Hotel Rescue & Offline Itinerary Cache (October slice)

> Status: READY TO IMPLEMENT. Paste this entire file to Genie Code.
> Land via PR to main, not direct push. Owner has no laptop -- unit and
> widget tests + flutter analyze in CI.

Canonical spec: `docs/specs/SPEC-04-offline-vault.md` (October Scope section)
Driver card UI: `docs/specs/SPEC-12-show-driver-cards.md` (uses `DriverCardScreen` / `cache_place`)
Booking anchors: `docs/specs/SPEC-10-booking-anchors.md` (`booking_type: 'hotel'`)
Offline storage: `docs/specs/SPEC-02-offline-queue-and-sync.md` (`cache_trip` & `cache_place` in `OfflineDatabase`)
Rules: `docs/ENGINEERING_RULES.md` (R1, R3, R14, R16, R17)

## Goal

Provide the October field-test safety net when stranded with no connectivity:

1. **Offline Itinerary Reads (SPEC-02 & SPEC-04):**
   When `ItineraryController.load()` encounters a network error / offline state,
   it falls back to SQLite `cache_trip` and renders the cached itinerary
   instead of an error screen. On successful network loads, it updates `cache_trip`.
2. **Hotel Rescue Entry (<= 2 Taps):**
   Add a Shield icon button in the itinerary AppBar (`Icons.shield_outlined`).
   - If an accommodation/hotel booking exists in the itinerary, **1 tap** opens
     the hotel's full-screen `DriverCardScreen` from SQLite `cache_place`.
   - If no hotel booking exists yet, opens `HotelRescueSheet` with a calm,
     honest empty state (*"No hotel saved yet"*) and a 1-tap `"+ Add Hotel Booking"`
     action.
   - Never a spinner, never an unhandled error state.
3. **Instant Place Caching on Booking Creation:**
   When `AddBookingSheet` saves a booking (especially a hotel), pre-cache its
   place data directly into SQLite `cache_place` so it is immediately available
   for driver cards offline without waiting for a trip reload.
4. **Data Models Serialization:**
   Add `toJson()` to `TripNode` and `TripState` so trip states round-trip
   cleanly through SQLite `cache_trip`.

## Out of Scope for October (Do Not Build)

- `cache_vault` or `cache_asset` tables (full vault deferred per SPEC-04)
- Offline pass / boarding-pass QR tiles
- Emergency actions grid (police, embassy)
- Per-city phrase pack

## Deliverables in this PR

1. `mobile/lib/data/models.dart` -- Add `toJson()` to `TripNode` and `TripState`.
2. `mobile/lib/features/itinerary/itinerary_notifier.dart` -- Wire offline reads in `load()`: save to `cache_trip` on success; read from `cache_trip` on error/offline.
3. `mobile/lib/features/booking/add_booking_sheet.dart` -- Support `initialBookingType` (defaults to `'flight'`, can be `'hotel'`); pre-cache place data to `cache_place` on save.
4. `mobile/lib/features/rescue/hotel_rescue_sheet.dart` -- Hotel rescue helper & bottom sheet: finds hotel node in itinerary, or renders honest empty state with `"+ Add Hotel Booking"` button and quick list of other cached venues.
5. `mobile/lib/features/itinerary/itinerary_screen.dart` -- Add shield icon button in `appBar.actions` wired to hotel rescue.
6. `mobile/test/features/rescue/hotel_rescue_test.dart` and `mobile/test/itinerary_controller_test.dart` -- Unit tests verifying offline fallback reads, cache persistence, hotel rescue navigation, empty state degradation, and sabotage proofs.

---

## 1. Models Serialization

In `mobile/lib/data/models.dart`:

Add `toJson()` to `TripNode`:
```dart
  Map<String, dynamic> toJson() => {
        'node_id': nodeId,
        'venue_name': venueName,
        'venue_id': venueId,
        'scheduled_start': scheduledStart.toUtc().toIso8601String(),
        'duration_minutes': durationMinutes,
        'is_locked': isLocked,
        'status': status.name,
        'micro_location': microLocation,
        'vibe_tags': vibeTags,
        'lat': lat,
        'lng': lng,
        'opening_hours': openingHours,
        'names_local': namesLocal,
        'landmarks_local': landmarksLocal,
        'nearest_landmark': nearestLandmark,
        'node_kind': nodeKind,
        'booking_type': bookingType,
        'confirmation_code': confirmationCode,
        'booking_notes': bookingNotes,
        'import_source': importSource,
      };
```

Add `toJson()` to `TripState`:
```dart
  Map<String, dynamic> toJson() => {
        'trip_id': tripId,
        'user_id': userId,
        'current_context': {'mood': mood},
        'nodes': nodes.map((n) => n.toJson()).toList(),
      };
```

---

## 2. Offline Reads in `ItineraryController`

In `mobile/lib/features/itinerary/itinerary_notifier.dart`:

Update `load()` to read/write `cache_trip` in SQLite `OfflineDatabase`:

```dart
  Future<void> load() async {
    state = const ItineraryState(loading: true);
    try {
      final trip = await _ref.read(tripRepoProvider).getTrip(tripId);
      if (!mounted) return;
      state = ItineraryState(nodes: trip.nodes, loading: false);
      _preCachePlaces(trip.nodes);
      // Persist to SQLite cache_trip for offline reads
      try {
        final db = _ref.read(offlineDatabaseProvider);
        db.cacheTrip(tripId, jsonEncode(trip.toJson())).catchError((e) {
          debugPrint('[ItineraryController] Cache trip error: $e');
        });
      } catch (_) {}
    } catch (e) {
      if (!mounted) return;
      // SPEC-04: Offline fallback -- read from SQLite cache_trip
      try {
        final db = _ref.read(offlineDatabaseProvider);
        final cachedJson = await db.getCachedTrip(tripId);
        if (cachedJson != null && mounted) {
          final cachedMap = jsonDecode(cachedJson) as Map<String, dynamic>;
          final cachedTrip = TripState.fromJson(cachedMap);
          state = ItineraryState(
            nodes: cachedTrip.nodes,
            loading: false,
            banner: 'Offline: showing saved itinerary',
          );
          _preCachePlaces(cachedTrip.nodes);
          return;
        }
      } catch (cacheErr) {
        debugPrint('[ItineraryController] Offline cache read error: $cacheErr');
      }
      state = ItineraryState(loading: false, error: e);
    }
  }
```

In `applyEvent()`, when `result != null && result.updatedNodes.isNotEmpty`:
Also pre-cache places and persist the updated trip nodes to `cache_trip`.

---

## 3. Hotel Rescue Sheet & Navigation

Create `mobile/lib/features/rescue/hotel_rescue_sheet.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import '../booking/add_booking_sheet.dart';

/// Finds the primary accommodation/hotel node in an itinerary.
TripNode? findHotelNode(List<TripNode> nodes) {
  return nodes.where((n) {
    if (n.bookingType == 'hotel' || n.nodeKind == 'hotel') return true;
    if (n.nodeKind == 'booking' && n.bookingType == 'hotel') return true;
    final name = n.venueName.toLowerCase();
    return name.contains('hotel') || name.contains('resort') || name.contains('hostel');
  }).firstOrNull;
}

/// Helper to execute <= 2-tap hotel rescue navigation.
void openHotelRescue(BuildContext context, {required String tripId, required List<TripNode> nodes}) {
  final hotel = findHotelNode(nodes);
  if (hotel != null) {
    // 1-tap direct path: open full-screen driver card for the hotel
    final placeRef = hotel.venueId ?? hotel.venueName;
    context.push('/trip/$tripId/card/$placeRef');
  } else {
    // 2-tap path: show rescue sheet with honest empty state & add hotel action
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => HotelRescueSheet(tripId: tripId, availableNodes: nodes),
    );
  }
}

/// Honest, calm emergency sheet when no hotel is saved yet.
class HotelRescueSheet extends StatelessWidget {
  final String tripId;
  final List<TripNode> availableNodes;

  const HotelRescueSheet({
    super.key,
    required this.tripId,
    required this.availableNodes,
  });

  @override
  Widget build(BuildContext context) {
    final otherPlaces = availableNodes.where((n) => n.venueName.isNotEmpty).toList();

    return Padding(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.shield_outlined, color: AppColors.accent, size: 24),
              const SizedBox(width: AppSpacing.sm),
              Text('Hotel Rescue', style: AppTypography.h2),
            ],
          ),
          const SizedBox(height: AppSpacing.base),
          Text(
            'No hotel saved yet.',
            style: AppTypography.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Save your hotel address so you can show taxi drivers even with no internet connection.',
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
          const SizedBox(height: AppSpacing.lg),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () {
                Navigator.of(context).pop();
                showModalBottomSheet(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => AddBookingSheet(
                    tripId: tripId,
                    initialBookingType: 'hotel',
                  ),
                );
              },
              icon: const Icon(Icons.hotel),
              label: const Text('Add Hotel Booking'),
            ),
          ),
          if (otherPlaces.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            const Divider(),
            const SizedBox(height: AppSpacing.sm),
            Text('Or show a driver another saved stop:', style: AppTypography.label),
            const SizedBox(height: AppSpacing.sm),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 180),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: otherPlaces.length,
                itemBuilder: (context, i) {
                  final place = otherPlaces[i];
                  return ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.place_outlined, size: 20),
                    title: Text(place.venueName, style: AppTypography.bodyMedium),
                    trailing: const Icon(Icons.chevron_right, size: 18),
                    onTap: () {
                      Navigator.of(context).pop();
                      final placeRef = place.venueId ?? place.venueName;
                      context.push('/trip/$tripId/card/$placeRef');
                    },
                  );
                },
              ),
            ),
          ],
          const SizedBox(height: AppSpacing.base),
        ],
      ),
    );
  }
}
```

---

## 4. `AddBookingSheet` Enhancements

In `mobile/lib/features/booking/add_booking_sheet.dart`:
- Accept optional `initialBookingType` parameter (`String initialBookingType = 'flight'`) and initialize `_bookingType = widget.initialBookingType`.
- When saving, immediately pre-cache place data into SQLite `cache_place`:
  ```dart
  try {
    final db = ref.read(offlineDatabaseProvider);
    final placeData = PlaceDriverCardData(
      placeRef: title,
      venueName: title,
      microLocation: _codeController.text.trim().isNotEmpty ? 'Confirmation: ${_codeController.text.trim()}' : null,
      nearestLandmark: _notesController.text.trim().isNotEmpty ? _notesController.text.trim() : null,
    );
    db.cachePlace(title, placeData.serialize()).catchError((_) {});
  } catch (_) {}
  ```

---

## 5. Itinerary Screen Shield Affordance

In `mobile/lib/features/itinerary/itinerary_screen.dart`:
In `AppBar.actions`:
```dart
          IconButton(
            icon: const Icon(Icons.shield_outlined),
            tooltip: 'Hotel Rescue',
            onPressed: () => openHotelRescue(
              context,
              tripId: tripId,
              nodes: state.nodes,
            ),
          ),
```

---

## 6. Tests & Sabotage Proofs (R17)

Create `mobile/test/features/rescue/hotel_rescue_test.dart`:

1. **`findHotelNode identifies hotel booking type`**:
   - Given a list with flight and hotel, returns the hotel node.
2. **`findHotelNode identifies venue with hotel keyword fallback`**:
   - Given a list with an activity named "Maison Souvannaphoum Hotel", returns it.
3. **`findHotelNode returns null when no hotel exists`**:
   - Given an activity-only list, returns null.
4. **`TripState toJson and fromJson roundtrip cleanly`**:
   - Validates that `TripState.fromJson(trip.toJson())` preserves all fields.

In `mobile/test/itinerary_controller_test.dart`:
5. **`offline load falls back to cached trip when network fails`**:
   - Mock `repo.getTrip('t1')` to throw `NetworkException()`.
   - Seed `mockDb.getCachedTrip('t1')` with valid serialized `TripState`.
   - `ItineraryController.load()` produces `state.loading == false` and `state.nodes.length == 1`.
6. **`successful load caches trip to SQLite cache_trip`**:
   - When `repo.getTrip` succeeds, verifies `mockDb.cacheTrip('t1', any())` was called.

### Sabotage Proofs (R17)
- **Sabotage 1:** In `ItineraryController.load()`, delete the `getCachedTrip` catch fallback.
  - Named test `offline load falls back to cached trip when network fails` must FAIL.
- **Sabotage 2:** In `findHotelNode`, return null even when a hotel node exists.
  - Named test `findHotelNode identifies hotel booking type` must FAIL.

---

## Proof Checklist before PR

- `grep -rn '\\$' mobile/lib` -- clean (only `upgrade_screen` price strings) (R1)
- `flutter analyze --no-fatal-infos` -- 0 errors, 0 warnings
- `flutter test` -- all unit & widget tests pass
- Python: `pytest -q -ra` -- 0 failures, drift guard green, `ruff check .` clean
- Pure ASCII in all docs and comments (R14)

## PR Details

- Branch: `feat/spec-04-hotel-rescue`
- Title: `feat(mobile): SPEC-04 hotel rescue card, offline itinerary cache fallback`
- Body: Summary of deliverables, verification evidence, sabotage proofs.
