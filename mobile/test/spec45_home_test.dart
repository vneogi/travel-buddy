// SPEC-45 item 1: Home screen featured trip appears above Create.
//
// UNVERIFIED: flutter test has not been run on this host.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/home/home_controller.dart';
import 'package:travel_buddy/features/home/home_screen.dart';

void main() {
  group('HomeScreen featured trip ordering', () {
    testWidgets('featured trip card appears before Create card',
        (tester) async {
      final snapshot = HomeSnapshot(
        trips: const [],
        supportedRegions: const ['vientiane_laos'],
        supportedCorridors: const [],
        featuredTrip: FeaturedTrip(
          tripId: 'trip-1',
          geoRegion: 'vientiane_laos',
        ),
        fromCache: false,
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            homeSnapshotProvider
                .overrideWith((ref) => Future.value(snapshot)),
          ],
          child: const MaterialApp(home: HomeScreen()),
        ),
      );
      await tester.pumpAndSettle();

      // Both cards must exist.
      final featuredFinder = find.byKey(const Key('featured_trip_card'));
      final createFinder = find.byKey(const Key('create_trip_card'));
      expect(featuredFinder, findsOneWidget);
      expect(createFinder, findsOneWidget);

      // Featured must appear ABOVE Create in the widget tree.
      final featuredOffset = tester.getTopLeft(featuredFinder);
      final createOffset = tester.getTopLeft(createFinder);
      expect(featuredOffset.dy, lessThan(createOffset.dy),
          reason: 'Featured trip card must be above Create card');
    });
  });
}
