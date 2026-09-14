import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/create_trip/create_trip_screen.dart';
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
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Where to next?'), findsOneWidget);
    expect(find.text('Create a trip'), findsOneWidget);
    expect(find.textContaining('No trips yet'), findsOneWidget);
  }, timeout: const Timeout(Duration(seconds: 20)));

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
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Dubai Uae'), findsOneWidget);
    expect(find.textContaining('2 bookings'), findsOneWidget);
    expect(find.textContaining('Showing saved trips while offline'), findsOneWidget);
  }, timeout: const Timeout(Duration(seconds: 20)));

  testWidgets('create card opens guided wizard', (tester) async {
    final router = GoRouter(
      routes: [
        GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
        GoRoute(
          path: '/trip/create',
          builder: (_, __) => const CreateTripScreen(),
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homeSnapshotProvider.overrideWith(
            (_) async => const HomeSnapshot(
              supportedRegions: ['luang_prabang_laos', 'dubai_uae'],
              trips: [],
              createTripOptions: CreateTripOptions(
                partyTypes: [],
                interests: [],
                maxDaysByRegion: {'luang_prabang_laos': 5, 'dubai_uae': 4},
              ),
            ),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // Tap the create card
    await tester.tap(find.text('Create a trip'));
    await tester.pumpAndSettle();

    // Wizard step 1 should be visible
    expect(find.text('Where are you going?'), findsOneWidget);
  }, timeout: const Timeout(Duration(seconds: 20)));
}
