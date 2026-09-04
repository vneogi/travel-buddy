import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/home/home_controller.dart';
import 'package:travel_buddy/features/home/home_screen.dart';

class _MockTripRepository extends Mock implements TripRepository {}

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

  testWidgets('create posts the selected laos region', (tester) async {
    registerFallbackValue(DateTime.utc(2026, 10, 5));
    final repository = _MockTripRepository();
    when(
      () => repository.create(
        startDate: any(named: 'startDate'),
        geoRegion: any(named: 'geoRegion'),
        mood: any(named: 'mood'),
      ),
    ).thenAnswer(
      (_) async => const TripState(tripId: 'laos-1', userId: 'u1', nodes: []),
    );

    final router = GoRouter(
      routes: [
        GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
        GoRoute(
          path: '/trip/:tripId',
          builder: (_, __) => const Scaffold(body: Text('trip opened')),
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          tripRepoProvider.overrideWithValue(repository),
          homeSnapshotProvider.overrideWith(
            (_) async => const HomeSnapshot(
              supportedRegions: ['luang_prabang_laos', 'dubai_uae'],
              trips: [],
            ),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.text('Create a trip'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();

    final captured = verify(
      () => repository.create(
        startDate: any(named: 'startDate'),
        geoRegion: captureAny(named: 'geoRegion'),
        mood: any(named: 'mood'),
      ),
    ).captured;
    expect(captured.single, 'luang_prabang_laos');
    expect(find.text('trip opened'), findsOneWidget);
  }, timeout: const Timeout(Duration(seconds: 20)));
}
