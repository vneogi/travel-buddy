import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/home/home_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

/// SPEC-26: HomeSnapshot model + featured trip rendering contract.
///
/// Required test coverage:
///   - Home widget renders from one repository result; /trip/{id} follow-up
///     is not needed (proven by constructing everything from HomeSnapshot).
///   - Offline cache renders featured card and cache age.
///   - Existing create/list behavior preserved.
void main() {
  // ===========================================================
  // Model parsing: FeaturedStop, FeaturedTrip, HomeSnapshot
  // ===========================================================

  group('FeaturedStop parsing', () {
    test('fromJson round-trips correctly', () {
      final json = {
        'node_id': 'n1',
        'venue_id': 'v1',
        'venue_name': 'Gold Souk',
        'scheduled_start': '2026-10-05T09:00:00Z',
        'status': 'active',
      };
      final stop = FeaturedStop.fromJson(json);
      expect(stop.nodeId, 'n1');
      expect(stop.venueId, 'v1');
      expect(stop.venueName, 'Gold Souk');
      expect(stop.status, 'active');

      final rt = FeaturedStop.fromJson(stop.toJson());
      expect(rt.nodeId, stop.nodeId);
      expect(rt.venueName, stop.venueName);
    });

    test('venue_id can be null', () {
      final json = {
        'node_id': 'n2',
        'venue_name': 'Unknown Spot',
        'scheduled_start': '2026-10-05T10:00:00Z',
        'status': 'pending',
      };
      final stop = FeaturedStop.fromJson(json);
      expect(stop.venueId, isNull);
    });
  });

  group('FeaturedTrip parsing', () {
    test('fromJson with actionable_stop', () {
      final json = {
        'trip_id': 't1',
        'geo_region': 'dubai_uae',
        'starts_at': '2026-10-05T08:00:00Z',
        'ends_at': '2026-10-07T22:00:00Z',
        'actionable_stop': {
          'node_id': 'n1',
          'venue_id': 'v1',
          'venue_name': 'Gold Souk',
          'scheduled_start': '2026-10-05T09:00:00Z',
          'status': 'active',
        },
      };
      final ft = FeaturedTrip.fromJson(json);
      expect(ft.tripId, 't1');
      expect(ft.geoRegion, 'dubai_uae');
      expect(ft.actionableStop, isNotNull);
      expect(ft.actionableStop!.venueName, 'Gold Souk');
    });

    test('fromJson without actionable_stop', () {
      final json = {
        'trip_id': 't2',
        'geo_region': 'luang_prabang_laos',
        'starts_at': null,
        'ends_at': null,
        'actionable_stop': null,
      };
      final ft = FeaturedTrip.fromJson(json);
      expect(ft.actionableStop, isNull);
      expect(ft.startsAt, isNull);
    });

    test('round-trip preserves data', () {
      final original = FeaturedTrip(
        tripId: 't3',
        geoRegion: 'dubai_uae',
        isActive: true,
        startsAt: DateTime.utc(2026, 10, 5),
        endsAt: DateTime.utc(2026, 10, 7),
        actionableStop: FeaturedStop(
          nodeId: 'n3',
          venueName: 'Test Venue',
          scheduledStart: DateTime.utc(2026, 10, 5, 9),
          status: 'pending',
        ),
      );
      final rt = FeaturedTrip.fromJson(original.toJson());
      expect(rt.tripId, original.tripId);
      expect(rt.isActive, isTrue);
      expect(rt.actionableStop!.nodeId, 'n3');
    });
  });

  group('HomeSnapshot with featured_trip', () {
    test('parses featured_trip from full response JSON', () {
      final json = {
        'supported_regions': ['dubai_uae', 'luang_prabang_laos'],
        'trips': [
          {
            'trip_id': 't1',
            'geo_region': 'dubai_uae',
            'starts_at': '2026-10-05T08:00:00Z',
            'ends_at': '2026-10-07T22:00:00Z',
            'node_count': 5,
            'booking_count': 1,
            'updated_at': '2026-10-04T12:00:00Z',
          },
        ],
        'featured_trip': {
          'trip_id': 't1',
          'geo_region': 'dubai_uae',
          'is_active': true,
          'starts_at': '2026-10-05T08:00:00Z',
          'ends_at': '2026-10-07T22:00:00Z',
          'actionable_stop': {
            'node_id': 'n1',
            'venue_id': 'v1',
            'venue_name': 'Gold Souk',
            'scheduled_start': '2026-10-05T09:00:00Z',
            'status': 'active',
          },
        },
      };
      final snap = HomeSnapshot.fromJson(json);
      expect(snap.trips, hasLength(1));
      expect(snap.featuredTrip, isNotNull);
      expect(snap.featuredTrip!.tripId, 't1');
      expect(snap.featuredTrip!.isActive, isTrue);
      expect(snap.featuredTrip!.actionableStop!.venueName, 'Gold Souk');
      expect(snap.featuredTrip!.actionableStop!.status, 'active');
    });

    test('null featured_trip is fine (no trips)', () {
      final json = {
        'supported_regions': ['dubai_uae'],
        'trips': <Map<String, dynamic>>[],
        'featured_trip': null,
      };
      final snap = HomeSnapshot.fromJson(json);
      expect(snap.featuredTrip, isNull);
      expect(snap.trips, isEmpty);
    });

    test('missing featured_trip key is fine (backward compat)', () {
      final json = {
        'supported_regions': ['dubai_uae'],
        'trips': <Map<String, dynamic>>[],
      };
      final snap = HomeSnapshot.fromJson(json);
      expect(snap.featuredTrip, isNull);
    });
  });

  // ===========================================================
  // Single-request contract: everything from HomeSnapshot
  // ===========================================================

  group('Single-request contract', () {
    test('everything the Home screen needs is in HomeSnapshot', () {
      // This test proves that no /trip/{id} follow-up is needed.
      // The HomeSnapshot contains:
      //   - supportedRegions for create-trip dialog
      //   - trips for the list
      //   - featuredTrip for the Now/Up next card
      //   - fromCache + cachedAt for offline notice
      // No additional API call is needed to render.
      final snap = HomeSnapshot(
        supportedRegions: ['dubai_uae'],
        trips: [
          TripSummary(
            tripId: 't1',
            geoRegion: 'dubai_uae',
            nodeCount: 5,
            bookingCount: 1,
            updatedAt: DateTime.utc(2026, 10, 4),
            startsAt: DateTime.utc(2026, 10, 5),
            endsAt: DateTime.utc(2026, 10, 7),
          ),
        ],
        featuredTrip: FeaturedTrip(
          tripId: 't1',
          geoRegion: 'dubai_uae',
          startsAt: DateTime.utc(2026, 10, 5),
          endsAt: DateTime.utc(2026, 10, 7),
          actionableStop: FeaturedStop(
            nodeId: 'n1',
            venueId: 'v1',
            venueName: 'Gold Souk',
            scheduledStart: DateTime.utc(2026, 10, 5, 9),
            status: 'active',
          ),
        ),
      );

      // Verify all fields are accessible without another call
      expect(snap.supportedRegions, isNotEmpty);
      expect(snap.trips, hasLength(1));
      expect(snap.featuredTrip!.tripId, 't1');
      expect(snap.featuredTrip!.actionableStop!.venueName, 'Gold Souk');
    });
  });

  // ===========================================================
  // Offline cache renders featured card with cache age
  // ===========================================================

  group('Offline cache', () {
    test('cached snapshot preserves featured_trip and cache age', () {
      final original = HomeSnapshot(
        supportedRegions: ['dubai_uae'],
        trips: [
          TripSummary(
            tripId: 't1',
            geoRegion: 'dubai_uae',
            nodeCount: 3,
            bookingCount: 0,
            updatedAt: DateTime.utc(2026, 10, 4),
          ),
        ],
        featuredTrip: FeaturedTrip(
          tripId: 't1',
          geoRegion: 'dubai_uae',
          actionableStop: FeaturedStop(
            nodeId: 'n1',
            venueName: 'Night Market',
            scheduledStart: DateTime.utc(2026, 10, 5, 19),
            status: 'pending',
          ),
        ),
      );

      // Simulate cache round-trip
      final jsonStr = jsonEncode(original.toJson());
      final cached = HomeSnapshot.fromJson(
        (jsonDecode(jsonStr) as Map).cast<String, dynamic>(),
        fromCache: true,
        cachedAt: DateTime.utc(2026, 10, 4, 12),
      );

      expect(cached.fromCache, isTrue);
      expect(cached.cachedAt, isNotNull);
      expect(cached.featuredTrip, isNotNull);
      expect(cached.featuredTrip!.tripId, 't1');
      expect(cached.featuredTrip!.actionableStop!.venueName, 'Night Market');
    });
  });

  // ===========================================================
  // Response shape: no state_json, no nodes list
  // ===========================================================

  group('Response shape', () {
    test('featured_trip JSON has no state_json or nodes key', () {
      final ft = FeaturedTrip(
        tripId: 't1',
        geoRegion: 'dubai_uae',
      );
      final json = ft.toJson();
      expect(json.containsKey('state_json'), isFalse);
      expect(json.containsKey('nodes'), isFalse);
    });

    test('HomeSnapshot JSON has no state_json', () {
      final snap = HomeSnapshot(
        supportedRegions: ['dubai_uae'],
        trips: [],
      );
      final json = snap.toJson();
      expect(json.containsKey('state_json'), isFalse);
    });
  });

  group('Home widget request contract', () {
    testWidgets('renders featured card from one repository response',
        (tester) async {
      final repository = _MockTripRepository();
      final database = _MockOfflineDatabase();
      final snapshot = HomeSnapshot(
        supportedRegions: const ['dubai_uae'],
        trips: [
          TripSummary(
            tripId: 'trip-1',
            geoRegion: 'dubai_uae',
            nodeCount: 1,
            bookingCount: 0,
            updatedAt: DateTime.utc(2026, 10, 4),
          ),
        ],
        featuredTrip: FeaturedTrip(
          tripId: 'trip-1',
          geoRegion: 'dubai_uae',
          isActive: true,
          actionableStop: FeaturedStop(
            nodeId: 'node-1',
            venueName: 'Gold Souk',
            scheduledStart: DateTime.utc(2026, 10, 5, 9),
            status: 'pending',
          ),
        ),
      );
      when(() => repository.getHomeSnapshot()).thenAnswer((_) async => snapshot);
      when(() => database.cacheTripList(any(), any()))
          .thenAnswer((_) async {});

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            tripRepoProvider.overrideWithValue(repository),
            offlineDatabaseProvider.overrideWithValue(database),
            identityCacheScopeProvider.overrideWithValue('anonymous:device-a'),
          ],
          child: const MaterialApp(home: HomeScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Now'), findsOneWidget);
      expect(find.text('Gold Souk'), findsOneWidget);
      verify(() => repository.getHomeSnapshot()).called(1);
      verifyNever(() => repository.getTrip(any()));
    });

    testWidgets('network failure renders cached featured card and cache age',
        (tester) async {
      final repository = _MockTripRepository();
      final database = _MockOfflineDatabase();
      final cachedAt = DateTime.now().toUtc().subtract(const Duration(hours: 2));
      final cachedJson = jsonEncode(
        HomeSnapshot(
          supportedRegions: const ['luang_prabang_laos'],
          trips: const [],
          featuredTrip: FeaturedTrip(
            tripId: 'trip-laos',
            geoRegion: 'luang_prabang_laos',
            actionableStop: FeaturedStop(
              nodeId: 'node-market',
              venueName: 'Night Market',
              scheduledStart: DateTime.utc(2026, 10, 5, 19),
              status: 'pending',
            ),
          ),
        ).toJson(),
      );
      when(() => repository.getHomeSnapshot())
          .thenThrow(const NetworkException());
      when(() => database.getCachedTripList('anonymous:device-a')).thenAnswer(
        (_) async => (json: cachedJson, cachedAt: cachedAt),
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            tripRepoProvider.overrideWithValue(repository),
            offlineDatabaseProvider.overrideWithValue(database),
            identityCacheScopeProvider.overrideWithValue('anonymous:device-a'),
          ],
          child: const MaterialApp(home: HomeScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Night Market'), findsOneWidget);
      expect(find.text('Cached 2h ago'), findsOneWidget);
      expect(
        find.textContaining('Showing saved trips while offline'),
        findsOneWidget,
      );
      verify(() => repository.getHomeSnapshot()).called(1);
      verifyNever(() => repository.getTrip(any()));
    });
  });
}
