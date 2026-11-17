// SPEC-52: markers from the cached home snapshot (offline path).
//
// Builds the snapshot exactly as the home controller's NetworkException
// fallback does: HomeSnapshot.fromJson(..., fromCache: true, cachedAt:).
// No socket, no repository.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/create_trip/existing_trip_dates.dart';
import 'package:travel_buddy/widgets/existing_trip_date_range_picker.dart';

final _cachedAt = DateTime.utc(2026, 11, 30, 8);

Map<String, dynamic> _tripJson({String? startsAt, String? endsAt}) => {
      'trip_id': 'trip-cached',
      'geo_region': 'luang_prabang_laos',
      'starts_at': startsAt,
      'ends_at': endsAt,
      'node_count': 3,
      'booking_count': 0,
      'updated_at': '2026-11-30T08:00:00Z',
    };

HomeSnapshot _cached(List<Map<String, dynamic>> trips) => HomeSnapshot.fromJson(
      {'supported_regions': <String>[], 'trips': trips},
      fromCache: true,
      cachedAt: _cachedAt,
    );

// 09:00 local Dec 10 to 17:00 local Dec 12 in Luang Prabang (UTC+7).
final _oneTrip = _tripJson(
  startsAt: '2026-12-10T02:00:00Z',
  endsAt: '2026-12-12T10:00:00Z',
);

final _expectedDays = {
  DateTime(2026, 12, 10),
  DateTime(2026, 12, 11),
  DateTime(2026, 12, 12),
};

Future<void> _openPicker(WidgetTester t, Set<DateTime> occupied) async {
  await t.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => Scaffold(
        body: Center(
          child: ElevatedButton(
            onPressed: () => showExistingTripDateRangePicker(
              context: context,
              firstDate: DateTime(2026, 12, 1),
              lastDate: DateTime(2027, 12, 31),
              occupiedDays: occupied,
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  ));
  await t.tap(find.text('open'));
  await t.pumpAndSettle();
  expect(find.text('December 2026'), findsOneWidget);
}

Finder get _anyMarker => find.byWidgetPredicate(
      (w) => w.key is ValueKey<String> &&
          (w.key! as ValueKey<String>).value.startsWith('marker-'),
    );

void main() {
  test('cached_home_snapshot_drives_markers', () {
    final snapshot = _cached([_oneTrip]);
    expect(snapshot.fromCache, isTrue);
    expect(snapshot.cachedAt, _cachedAt);
    expect(snapshot.trips, hasLength(1));
    expect(occupiedDaysFromTrips(snapshot.trips), _expectedDays);
  });

  testWidgets('cached_snapshot_markers_render_in_picker', (t) async {
    final days = occupiedDaysFromTrips(_cached([_oneTrip]).trips);
    await _openPicker(t, days);
    expect(find.byKey(const Key('marker-2026-12-10')), findsOneWidget);
    expect(find.byKey(const Key('marker-2026-12-11')), findsOneWidget);
    expect(find.byKey(const Key('marker-2026-12-12')), findsOneWidget);
    expect(find.byKey(const Key('marker-2026-12-13')), findsNothing);
  });

  testWidgets('cached_empty_trip_list_shows_no_markers', (t) async {
    final empty = _cached(const []);
    expect(empty.fromCache, isTrue);
    expect(occupiedDaysFromTrips(empty.trips), isEmpty);

    final openEnded = _cached([
      _tripJson(startsAt: '2026-12-10T02:00:00Z', endsAt: null),
    ]);
    final days = occupiedDaysFromTrips(openEnded.trips);
    expect(days, isEmpty);

    await _openPicker(t, days);
    expect(_anyMarker, findsNothing);
  });
}
