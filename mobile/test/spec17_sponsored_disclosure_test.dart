// SPEC-17 decision 15: sponsored search disclosure slice -- Flutter tests.
//
// Covers:
//   - VenueSearchResult parses actual backend-shaped fixture (flat, no nested venue).
//   - sponsoredBoostApplied round-trips correctly.
//   - SwapSheet displays "Sponsored" label + explanation for boosted venues.
//   - SwapSheet does NOT display label for organic venues.
//   - Sabotage: removing the label while keeping the boost fails the render test.
//   - Widget test drives SwapSheet through the repository provider.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/swap_sheet/swap_sheet.dart';

class _MockTripRepository extends Mock implements TripRepository {}

// ---------------------------------------------------------------------------
// Fixtures -- actual backend-shaped flat payloads
// ---------------------------------------------------------------------------

const _boostedJson = {
  'venue_id': 'v-sponsored-1',
  'name': 'Luxury Lounge',
  'description': 'Premium waterfront dining',
  'micro_location': 'Marina Walk',
  'vibe_tags': ['luxury', 'waterfront'],
  'distance_km': 1.2,
  'is_sponsored': true,
  'sponsored_boost_applied': true,
};

const _organicJson = {
  'venue_id': 'v-organic-1',
  'name': 'Street Bites',
  'description': 'Local street food corner',
  'micro_location': 'Old Souk',
  'vibe_tags': ['budget', 'authentic'],
  'distance_km': 0.5,
  'is_sponsored': false,
  'sponsored_boost_applied': false,
};

const _sponsoredNoBoostJson = {
  'venue_id': 'v-sponsored-nobid',
  'name': 'Partner Cafe',
  'description': 'Partner venue with no active bid',
  'micro_location': 'City Walk',
  'vibe_tags': ['cafe'],
  'distance_km': null,
  'is_sponsored': true,
  'sponsored_boost_applied': false,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

TripState _minimalTrip() => const TripState(
      tripId: 'trip-1',
      userId: 'u1',
      geoRegion: 'dubai_uae',
      nodes: [],
      locationLat: 25.1972,
      locationLng: 55.2744,
    );

TripState _tripWithCurrentVenue() => TripState(
      tripId: 'trip-1',
      userId: 'u1',
      geoRegion: 'dubai_uae',
      locationLat: 25.1972,
      locationLng: 55.2744,
      nodes: [
        TripNode(
          nodeId: 'node-1',
          venueName: 'Luxury Lounge',
          venueId: 'v-sponsored-1',
          scheduledStart: DateTime.utc(2026, 10, 2, 9),
          durationMinutes: 90,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const ['luxury'],
        ),
      ],
    );

Widget _wrapSheet({
  required _MockTripRepository repo,
  required TripState tripState,
}) {
  return ProviderScope(
    overrides: [
      tripRepoProvider.overrideWithValue(repo),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: SwapSheet(
          tripId: tripState.tripId,
          targetNodeId: 'node-1',
          tripState: tripState,
        ),
      ),
    ),
  );
}

void main() {
  // -------------------------------------------------------------------------
  // Model parsing tests
  // -------------------------------------------------------------------------

  group('VenueSearchResult model parsing', () {
    test('parses boosted venue from flat backend JSON', () {
      final v = VenueSearchResult.fromJson(_boostedJson);
      expect(v.venueId, 'v-sponsored-1');
      expect(v.name, 'Luxury Lounge');
      expect(v.description, 'Premium waterfront dining');
      expect(v.microLocation, 'Marina Walk');
      expect(v.vibeTags, ['luxury', 'waterfront']);
      expect(v.distanceKm, 1.2);
      expect(v.isSponsored, true);
      expect(v.sponsoredBoostApplied, true);
    });

    test('parses organic venue from flat backend JSON', () {
      final v = VenueSearchResult.fromJson(_organicJson);
      expect(v.venueId, 'v-organic-1');
      expect(v.isSponsored, false);
      expect(v.sponsoredBoostApplied, false);
    });

    test('parses sponsored-but-unboosted venue', () {
      final v = VenueSearchResult.fromJson(_sponsoredNoBoostJson);
      expect(v.isSponsored, true);
      expect(v.sponsoredBoostApplied, false);
    });

    test('fixture has no nested venue key', () {
      expect(_boostedJson.containsKey('venue'), false);
      expect(_organicJson.containsKey('venue'), false);
    });

    test('missing sponsored_boost_applied defaults to false', () {
      final minimal = {
        'venue_id': 'v-min',
        'name': 'Minimal',
        'description': '',
        'micro_location': '',
        'vibe_tags': <String>[],
        'is_sponsored': false,
      };
      final v = VenueSearchResult.fromJson(minimal);
      expect(v.sponsoredBoostApplied, false);
    });
  });

  // -------------------------------------------------------------------------
  // Widget tests -- SwapSheet disclosure
  // -------------------------------------------------------------------------

  group('SwapSheet sponsored disclosure', () {
    late _MockTripRepository repo;

    setUp(() {
      repo = _MockTripRepository();
    });

    testWidgets('boosted venue shows Sponsored label and explanation',
        (tester) async {
      when(() => repo.searchVenues(
            query: any(named: 'query'),
            lat: any(named: 'lat'),
            lng: any(named: 'lng'),
            topK: any(named: 'topK'),
          )).thenAnswer((_) async => [
            VenueSearchResult.fromJson(_boostedJson),
            VenueSearchResult.fromJson(_organicJson),
          ]);

      await tester.pumpWidget(_wrapSheet(
        repo: repo,
        tripState: _minimalTrip(),
      ));
      await tester.pumpAndSettle();

      // The boosted venue must show the Sponsored label.
      expect(find.text('Sponsored'), findsOneWidget);
      expect(
        find.text('Paid placement influenced this ranking.'),
        findsOneWidget,
      );
    }, timeout: const Timeout(Duration(seconds: 20)));

    testWidgets('organic venue does NOT show Sponsored label',
        (tester) async {
      when(() => repo.searchVenues(
            query: any(named: 'query'),
            lat: any(named: 'lat'),
            lng: any(named: 'lng'),
            topK: any(named: 'topK'),
          )).thenAnswer((_) async => [
            VenueSearchResult.fromJson(_organicJson),
          ]);

      await tester.pumpWidget(_wrapSheet(
        repo: repo,
        tripState: _minimalTrip(),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Sponsored'), findsNothing);
      expect(
        find.text('Paid placement influenced this ranking.'),
        findsNothing,
      );
    }, timeout: const Timeout(Duration(seconds: 20)));

    testWidgets('current venue is excluded from its own swap options',
        (tester) async {
      when(() => repo.searchVenues(
            query: any(named: 'query'),
            lat: any(named: 'lat'),
            lng: any(named: 'lng'),
            topK: any(named: 'topK'),
          )).thenAnswer((_) async => [
            VenueSearchResult.fromJson(_boostedJson),
            VenueSearchResult.fromJson(_organicJson),
          ]);

      await tester.pumpWidget(_wrapSheet(
        repo: repo,
        tripState: _tripWithCurrentVenue(),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Luxury Lounge'), findsNothing);
      expect(find.text('Street Bites'), findsOneWidget);
    }, timeout: const Timeout(Duration(seconds: 20)));

    testWidgets('vibe chips filter the rendered alternatives', (tester) async {
      when(() => repo.searchVenues(
            query: any(named: 'query'),
            lat: any(named: 'lat'),
            lng: any(named: 'lng'),
            topK: any(named: 'topK'),
          )).thenAnswer((_) async => [
            VenueSearchResult.fromJson(_boostedJson),
            VenueSearchResult.fromJson(_organicJson),
          ]);

      await tester.pumpWidget(_wrapSheet(
        repo: repo,
        tripState: _minimalTrip(),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Luxury Lounge'), findsOneWidget);
      expect(find.text('Street Bites'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilterChip, 'authentic'));
      await tester.pump();

      expect(find.text('Luxury Lounge'), findsNothing);
      expect(find.text('Street Bites'), findsOneWidget);
    }, timeout: const Timeout(Duration(seconds: 20)));

    testWidgets(
        'SABOTAGE: boosted result without Sponsored label must fail',
        (tester) async {
      // This test asserts the label IS present for a boosted result.
      // If someone removes the Sponsored label from SwapSheet while
      // keeping the data flag, this test fails -- that is the
      // sabotage proof from SPEC-17 decision 15.
      when(() => repo.searchVenues(
            query: any(named: 'query'),
            lat: any(named: 'lat'),
            lng: any(named: 'lng'),
            topK: any(named: 'topK'),
          )).thenAnswer((_) async => [
            VenueSearchResult.fromJson(_boostedJson),
          ]);

      await tester.pumpWidget(_wrapSheet(
        repo: repo,
        tripState: _minimalTrip(),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Sponsored'), findsOneWidget,
          reason: 'A boosted result MUST display the Sponsored label');
      expect(
        find.text('Paid placement influenced this ranking.'),
        findsOneWidget,
        reason: 'A boosted result MUST explain the ranking influence',
      );
    }, timeout: const Timeout(Duration(seconds: 20)));

    testWidgets('drives SwapSheet through the repository provider',
        (tester) async {
      when(() => repo.searchVenues(
            query: any(named: 'query'),
            lat: any(named: 'lat'),
            lng: any(named: 'lng'),
            topK: any(named: 'topK'),
          )).thenAnswer((_) async => [
            VenueSearchResult.fromJson(_boostedJson),
            VenueSearchResult.fromJson(_organicJson),
            VenueSearchResult.fromJson(_sponsoredNoBoostJson),
          ]);

      tester.view.physicalSize = const Size(800, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_wrapSheet(
        repo: repo,
        tripState: _minimalTrip(),
      ));
      await tester.pumpAndSettle();

      // Verify the repository was called.
      verify(() => repo.searchVenues(
            query: any(named: 'query'),
            lat: any(named: 'lat'),
            lng: any(named: 'lng'),
            topK: any(named: 'topK'),
          )).called(1);

      // Three venues rendered (sheet is short; use a tall surface so the
      // third row is not clipped by DraggableScrollableSheet).
      expect(find.text('Luxury Lounge'), findsOneWidget);
      expect(find.text('Street Bites'), findsOneWidget);
      expect(find.text('Partner Cafe'), findsOneWidget);

      // Only the boosted one has the Sponsored label.
      expect(find.text('Sponsored'), findsOneWidget);
    }, timeout: const Timeout(Duration(seconds: 20)));
  });
}
