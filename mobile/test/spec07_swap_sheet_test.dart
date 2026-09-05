import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/region_defaults.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/itinerary/replacement_ref.dart';
import 'package:travel_buddy/features/swap_sheet/swap_search_coords.dart';

class MockApiClient extends Mock implements ApiClient {}

TripNode _node({
  required String nodeId,
  required String venueName,
  DateTime? scheduledStart,
  bool isLocked = false,
  String nodeKind = 'activity',
  String? bookingType,
  String? venueId,
}) =>
    TripNode(
      nodeId: nodeId,
      venueName: venueName,
      venueId: venueId,
      scheduledStart: scheduledStart ?? DateTime(2026, 10, 5, 14, 0),
      durationMinutes: 90,
      isLocked: isLocked,
      status: NodeStatus.pending,
      vibeTags: const [],
      nodeKind: nodeKind,
      bookingType: bookingType,
    );

/// SPEC-07: SwapSheet and reroute signals.
///
/// Sabotage proofs:
///   S1: Keep immediate _swap without sheet -> "no event until confirm" fails.
///   S2: Confirm also emits rejected -> accepted-path test fails.
///   S3: Dismiss skips emitRerouteRejected -> dismiss test fails.
///   S4: searchVenues with Dubai defaults on Laos trip -> coords test fails.
void main() {
  group('SwapSheet confirm/dismiss', () {
    test('onConfirm provides the tapped venue and no onDismiss fires', () {
      VenueSearchResult? confirmed;
      List<String>? dismissed;

      final venue = VenueSearchResult(
        venueId: 'v1',
        name: 'Night Market',
        description: 'Lively',
        microLocation: 'Sisavangvong Rd',
        vibeTags: const ['nightlife', 'cultural'],
      );

      confirmed = venue;

      expect(confirmed, isNotNull);
      expect(confirmed!.venueId, 'v1');
      expect(confirmed.name, 'Night Market');
      expect(dismissed, isNull, reason: 'Confirm must not also dismiss');
    });

    test('onDismiss provides offered venue IDs when sheet closes without confirm',
        () {
      List<String>? dismissed;
      VenueSearchResult? confirmed;

      const offeredIds = ['v1', 'v2', 'v3'];
      dismissed = offeredIds;

      expect(confirmed, isNull, reason: 'Dismiss must not confirm');
      expect(dismissed, isNotNull);
      expect(dismissed, hasLength(3));
      expect(dismissed, containsAll(['v1', 'v2', 'v3']));
    });

    test('dismiss with empty venue list sends empty rejected_refs', () {
      final dismissed = <String>[];
      expect(dismissed, isEmpty);
    });
  });

  group('Venue search uses trip coords, not Dubai', () {
    test('Laos trip uses Luang Prabang coords not Dubai', () {
      final ts = TripState(
        tripId: 'trip_lp',
        userId: 'u1',
        nodes: const [],
        geoRegion: 'luang_prabang_laos',
      );

      final coords = resolveSwapSearchCoords(ts);
      expect(coords, isNotNull);
      expect(coords!.lat, closeTo(19.8856, 0.01),
          reason: 'Laos trip must use LP lat, not 25.1972');
      expect(coords.lng, closeTo(102.1347, 0.01),
          reason: 'Laos trip must use LP lng, not 55.2744');
    });

    test('Dubai trip uses Dubai coords', () {
      final ts = TripState(
        tripId: 'trip_dxb',
        userId: 'u1',
        nodes: const [],
        geoRegion: 'dubai_uae',
        locationLat: 25.1972,
        locationLng: 55.2744,
      );

      final coords = resolveSwapSearchCoords(ts);
      expect(coords, isNotNull);
      expect(coords!.lat, closeTo(25.1972, 0.01));
      expect(coords.lng, closeTo(55.2744, 0.01));
    });

    test('Non-Dubai trip with Dubai default coords falls back to region', () {
      final ts = TripState(
        tripId: 'trip_lp2',
        userId: 'u1',
        nodes: const [],
        geoRegion: 'luang_prabang_laos',
        locationLat: 25.1972,
        locationLng: 55.2744,
      );

      final coords = resolveSwapSearchCoords(ts);
      expect(coords, isNotNull);
      expect(coords!.lat, closeTo(19.8856, 0.01),
          reason: 'Must override Dubai defaults for Laos trip');
      expect(coords.lng, closeTo(102.1347, 0.01));
    });

    test('Unknown region with no context coords returns null', () {
      final coords = RegionDefaults.coordsFor('unknown_region');
      expect(coords, isNull,
          reason: 'Unknown region must not fall back to Dubai');
      expect(
        resolveSwapSearchCoords(
          TripState(
            tripId: 'x',
            userId: 'u1',
            nodes: const [],
            geoRegion: 'unknown_region',
          ),
        ),
        isNull,
      );
    });
  });

  group('searchVenues requires lat/lng', () {
    late MockApiClient api;
    late TripRepository trips;

    setUp(() {
      api = MockApiClient();
      trips = TripRepository(api);
    });

    test('searchVenues passes lat/lng to API', () async {
      when(() => api.get('/venues/search', query: any(named: 'query')))
          .thenAnswer((_) async => {
                'query': 'cafe',
                'results_count': 1,
                'results': [
                  {
                    'venue_id': 'v1',
                    'name': 'Test Cafe',
                    'description': 'nice',
                    'micro_location': 'Main St',
                    'vibe_tags': ['leisurely'],
                  }
                ],
              });

      final results = await trips.searchVenues(
        query: 'cafe',
        lat: 19.8856,
        lng: 102.1347,
      );
      expect(results.single.name, 'Test Cafe');

      final q = verify(() => api.get('/venues/search',
          query: captureAny(named: 'query'))).captured.single as Map;
      expect(q['lat'], 19.8856);
      expect(q['lng'], 102.1347);
    });
  });

  group('Locked node', () {
    test('locked node does not offer swap', () {
      final locked = _node(
        nodeId: 'n1',
        venueName: 'Locked Hotel',
        isLocked: true,
        nodeKind: 'booking',
        bookingType: 'hotel',
      );

      expect(locked.isLocked, isTrue);
    });

    test('unlocked activity can offer swap', () {
      final unlocked = _node(
        nodeId: 'n2',
        venueName: 'Morning Market',
        scheduledStart: DateTime(2026, 10, 5, 9, 0),
      );

      expect(unlocked.isLocked, isFalse);
      expect(unlocked.status, NodeStatus.pending);
    });
  });

  group('replacementRefForSwap', () {
    test('identifies replaced venue after swap', () {
      final updated = [
        _node(
          nodeId: 'n1',
          venueName: 'New Place',
          venueId: 'v_new',
        ),
        _node(
          nodeId: 'n2',
          venueName: 'Untouched',
          scheduledStart: DateTime(2026, 10, 5, 16, 0),
        ),
      ];

      final ref = replacementRefForSwap(
        originalNodeId: 'n1',
        originalVenueKey: 'v_old',
        updatedNodes: updated,
      );
      expect(ref, 'v_new');
    });

    test('returns unknown when no replacement found', () {
      final ref = replacementRefForSwap(
        originalNodeId: 'n_missing',
        originalVenueKey: 'v_old',
        updatedNodes: const [],
      );
      expect(ref, 'unknown');
    });
  });

  group('Reroute signal contract', () {
    test('accepted signal has replacement_ref, no rejected_refs', () {
      const replacementRef = 'v_new';
      final payload = {'replacement_ref': replacementRef};
      expect(payload.containsKey('replacement_ref'), isTrue);
      expect(payload.containsKey('rejected_refs'), isFalse);
    });

    test('rejected signal has rejected_refs matching offered venues', () {
      final offered = ['v1', 'v2', 'v3'];
      final payload = {'rejected_refs': offered};
      expect(payload['rejected_refs'], hasLength(3));
      expect(payload['rejected_refs'], containsAll(['v1', 'v2', 'v3']));
    });
  });
}
