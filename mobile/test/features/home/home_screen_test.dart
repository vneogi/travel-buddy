import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/home/home_controller.dart';
import 'package:travel_buddy/features/home/home_screen.dart';

void main() {
  testWidgets('home renders a designed empty state', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homeSnapshotProvider.overrideWith(
            (_) async => const HomeSnapshot(
              supportedRegions: ['dubai_uae'],
              trips: [],
            ),
          ),
        ],
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Where to next?'), findsOneWidget);
    expect(find.text('Create a trip'), findsOneWidget);
    expect(find.textContaining('No trips yet'), findsOneWidget);
  });

  testWidgets('home shows cached trip projection and offline state', (tester) async {
    final snapshot = HomeSnapshot(
      supportedRegions: const ['dubai_uae'],
      fromCache: true,
      trips: [
        TripSummary(
          tripId: 'trip-1',
          geoRegion: 'dubai_uae',
          startsAt: DateTime.utc(2026, 10, 4),
          nodeCount: 5,
          bookingCount: 2,
          updatedAt: DateTime.utc(2026, 8, 27),
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homeSnapshotProvider.overrideWith((_) async => snapshot),
        ],
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Dubai Uae'), findsOneWidget);
    expect(find.textContaining('2 bookings'), findsOneWidget);
    expect(find.textContaining('Showing saved trips while offline'), findsOneWidget);
  });
}
