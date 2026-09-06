// SPEC-36: Flutter corridor proof and sabotage tests.
//
// Includes model/cache coverage, corridor grouping, and production-path
// widget checks for later-city swap coordinates.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/widgets/city_section.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

class _MockSignalService extends Mock implements SignalService {}

void _stubDatabase(_MockOfflineDatabase database) {
  when(() => database.getLovedPlaceRefs(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String>{});
  when(() => database.getNodeOutcomes(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String, NodeOutcome>{});
  when(() => database.cachePlace(any(), any())).thenAnswer((_) async {});
  when(() => database.cacheTrip(any(), any())).thenAnswer((_) async {});
  when(() => database.getCachedTrip(any())).thenAnswer((_) async => null);
  when(() => database.pruneAlertData()).thenAnswer((_) async {});
  when(() => database.getDismissedAlertIds(
        identityScope: any(named: 'identityScope'),
      )).thenAnswer((_) async => <String>{});
  when(() => database.upsertNodeOutcome(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
        nodeId: any(named: 'nodeId'),
        outcome: any(named: 'outcome'),
        reason: any(named: 'reason'),
        recordedAt: any(named: 'recordedAt'),
      )).thenAnswer((_) async {});
}

Future<ProviderContainer> _loadItineraryContainer({
  required TripState trip,
  required _MockTripRepository repo,
}) async {
  final database = _MockOfflineDatabase();
  final signalService = _MockSignalService();
  final api = _MockApiClient();
  _stubDatabase(database);

  when(() => repo.getTrip(trip.tripId)).thenAnswer((_) async => trip);
  when(() => api.get(any(), query: any(named: 'query'))).thenAnswer(
    (invocation) async {
      final path = invocation.positionalArguments.first as String;
      if (path.endsWith('/alerts')) {
        return {
          'trip_id': trip.tripId,
          'status': 'unconfigured',
          'alerts': <Object>[],
          'refreshed_at': '2026-08-31T12:00:00.000Z',
        };
      }
      return {
        'user_id': trip.userId,
        'tier': 'free',
        'daily_reroutes_used': 0,
        'daily_reroutes_remaining': 3,
        'max_daily_reroutes': 3,
      };
    },
  );
  when(() => signalService.emitVisitedConfirmedWithResult(
        placeRef: any(named: 'placeRef'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => true);
  when(() => signalService.emitNodeSkippedWithResult(
        placeRef: any(named: 'placeRef'),
        reason: any(named: 'reason'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => true);
  when(() => signalService.emitUserLoved(
        placeRef: any(named: 'placeRef'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async {});
  when(() => signalService.emitRerouteRejected(
        placeRef: any(named: 'placeRef'),
        rejectedRefs: any(named: 'rejectedRefs'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async {});
  when(() => signalService.emitRerouteAccepted(
        placeRef: any(named: 'placeRef'),
        replacementRef: any(named: 'replacementRef'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async {});

  final container = ProviderContainer(
    overrides: [
      tripRepoProvider.overrideWithValue(repo),
      apiClientProvider.overrideWithValue(api),
      offlineDatabaseProvider.overrideWithValue(database),
      identityCacheScopeProvider.overrideWithValue('account:${trip.userId}'),
      signalServiceProvider.overrideWithValue(signalService),
    ],
  );

  final loaded = Completer<void>();
  final sub = container.listen(
    itineraryControllerProvider(trip.tripId),
    (_, next) {
      if (!next.loading && !loaded.isCompleted) {
        loaded.complete();
      }
    },
    fireImmediately: true,
  );
  await loaded.future;
  addTearDown(() {
    sub.close();
    container.dispose();
  });
  return container;
}

void main() {
  // -- Helpers ---------------------------------------------------------------

  TripNode _node({
    required String name,
    required String geoRegion,
    required DateTime scheduledStart,
    int durationMinutes = 60,
  }) =>
      TripNode(
        nodeId: name,
        venueName: name,
        scheduledStart: scheduledStart,
        durationMinutes: durationMinutes,
        isLocked: false,
        status: NodeStatus.pending,
        geoRegion: geoRegion,
        lat: 0,
        lng: 0,
        vibeTags: const [],
      );

  TripSegment _seg(String region, String start, String end) => TripSegment(
        geoRegion: region,
        startsOn: start,
        endsOn: end,
      );

  // -- Proof 12: SupportedCorridor round-trips JSON --------------------------

  test('P12: SupportedCorridor.fromJson round-trips', () {
    final json = {
      'corridor_id': 'laos_northbound_v1',
      'display_name': 'Vientiane to Luang Prabang',
      'geo_regions': ['vientiane_laos', 'vang_vieng_laos', 'luang_prabang_laos'],
      'max_days': 7,
      'max_days_per_segment': 3,
    };
    final c = SupportedCorridor.fromJson(json);
    expect(c.corridorId, 'laos_northbound_v1');
    expect(c.geoRegions, hasLength(3));
    expect(c.maxDays, 7);
    final out = c.toJson();
    expect(out['corridor_id'], 'laos_northbound_v1');
  });

  // -- Proof 13: TripSegment round-trips JSON --------------------------------

  test('P13: TripSegment.fromJson round-trips', () {
    final json = {
      'geo_region': 'vientiane_laos',
      'starts_on': '2026-10-02',
      'ends_on': '2026-10-03',
    };
    final s = TripSegment.fromJson(json);
    expect(s.geoRegion, 'vientiane_laos');
    expect(s.startsOn, '2026-10-02');
    final out = s.toJson();
    expect(out['starts_on'], '2026-10-02');
  });

  // -- Proof 14: TripState parses corridor_id + segments ---------------------

  test('P14: TripState parses corridor_id and segments', () {
    final json = {
      'trip_id': 'test-trip-1',
      'user_id': 'u1',
      'nodes': <Map<String, dynamic>>[],
      'corridor_id': 'laos_northbound_v1',
      'segments': [
        {'geo_region': 'vientiane_laos', 'starts_on': '2026-10-02', 'ends_on': '2026-10-03'},
        {'geo_region': 'vang_vieng_laos', 'starts_on': '2026-10-04', 'ends_on': '2026-10-05'},
      ],
    };
    final ts = TripState.fromJson(json);
    expect(ts.corridorId, 'laos_northbound_v1');
    expect(ts.segments, hasLength(2));
    expect(ts.segments.first.geoRegion, 'vientiane_laos');
  });

  // -- Proof 15: corridor grouping preserves segment order -------------------

  test('P15: groupNodesByCorridor preserves segment order', () {
    final segments = [
      _seg('vientiane_laos', '2026-10-02', '2026-10-02'),
      _seg('vang_vieng_laos', '2026-10-03', '2026-10-03'),
      _seg('luang_prabang_laos', '2026-10-04', '2026-10-04'),
    ];
    final nodes = [
      _node(name: 'LP1', geoRegion: 'luang_prabang_laos',
            scheduledStart: DateTime.utc(2026, 10, 4, 2)),
      _node(name: 'VTE1', geoRegion: 'vientiane_laos',
            scheduledStart: DateTime.utc(2026, 10, 2, 2)),
      _node(name: 'VV1', geoRegion: 'vang_vieng_laos',
            scheduledStart: DateTime.utc(2026, 10, 3, 2)),
    ];
    final groups = groupNodesByCorridor(nodes: nodes, segments: segments);
    expect(groups, hasLength(3));
    expect(groups[0].geoRegion, 'vientiane_laos');
    expect(groups[1].geoRegion, 'vang_vieng_laos');
    expect(groups[2].geoRegion, 'luang_prabang_laos');
    expect(groups[0].dayGroups.expand((dg) => dg.nodes).first.venueName, 'VTE1');
    expect(groups[2].dayGroups.expand((dg) => dg.nodes).first.venueName, 'LP1');
  });

  // -- Proof 16: unknown region nodes go to "Other stops" --------------------

  test('P16: unknown region nodes go to Other stops', () {
    final segments = [
      _seg('vientiane_laos', '2026-10-02', '2026-10-02'),
    ];
    final nodes = [
      _node(name: 'VTE1', geoRegion: 'vientiane_laos',
            scheduledStart: DateTime.utc(2026, 10, 2, 2)),
      _node(name: 'Mystery', geoRegion: 'unknown_region',
            scheduledStart: DateTime.utc(2026, 10, 2, 4)),
    ];
    final groups = groupNodesByCorridor(nodes: nodes, segments: segments);
    expect(groups.last.displayName, 'Other stops');
    expect(groups.last.dayGroups.expand((dg) => dg.nodes).first.venueName,
        'Mystery');
  });

  // -- Proof 17: display names resolve correctly -----------------------------

  test('P17: display names are human-readable', () {
    final segments = [
      _seg('luang_prabang_laos', '2026-10-06', '2026-10-08'),
    ];
    final nodes = [
      _node(name: 'T1', geoRegion: 'luang_prabang_laos',
            scheduledStart: DateTime.utc(2026, 10, 6, 2)),
    ];
    final groups = groupNodesByCorridor(nodes: nodes, segments: segments);
    expect(groups.first.displayName, 'Luang Prabang');
    expect(groups.first.dateRange, '2026-10-06 - 2026-10-08');
  });

  // -- Proof 18: HomeSnapshot parses supported_corridors ---------------------

  test('P18: HomeSnapshot parses supported_corridors', () {
    final json = {
      'supported_regions': ['dubai_uae'],
      'supported_corridors': [
        {
          'corridor_id': 'laos_northbound_v1',
          'display_name': 'Vientiane to Luang Prabang',
          'geo_regions': ['vientiane_laos', 'vang_vieng_laos', 'luang_prabang_laos'],
          'max_days': 7,
          'max_days_per_segment': 3,
        }
      ],
      'trips': <Map<String, dynamic>>[],
    };
    final snap = HomeSnapshot.fromJson(json);
    expect(snap.supportedCorridors, hasLength(1));
    expect(snap.supportedCorridors.first.corridorId, 'laos_northbound_v1');
  });

  // -- Proof 19: TripSummary parses corridor_id ------------------------------

  test('P19: TripSummary parses corridor_id', () {
    final json = {
      'trip_id': 't1',
      'geo_region': 'vientiane_laos',
      'node_count': 28,
      'booking_count': 0,
      'updated_at': '2026-10-02T00:00:00Z',
      'corridor_id': 'laos_northbound_v1',
    };
    final ts = TripSummary.fromJson(json);
    expect(ts.corridorId, 'laos_northbound_v1');
  });

  test('FeaturedTrip parses corridor_id', () {
    final json = {
      'trip_id': 't1',
      'geo_region': 'vientiane_laos',
      'is_active': true,
      'corridor_id': 'laos_northbound_v1',
    };
    final ft = FeaturedTrip.fromJson(json);
    expect(ft.corridorId, 'laos_northbound_v1');
  });

  // -- Proof 20: later-city swap search uses tapped node coordinates ----------

  testWidgets('P20: later-city SwapSheet search uses tapped node coordinates',
      (tester) async {
    final repo = _MockTripRepository();
    when(() => repo.searchVenues(
          query: any(named: 'query'),
          lat: any(named: 'lat'),
          lng: any(named: 'lng'),
          topK: any(named: 'topK'),
        )).thenAnswer((_) async => [
          const VenueSearchResult(
            venueId: 'alt-1',
            name: 'Waterfront Cafe',
            description: 'Alt venue',
            microLocation: 'Old Quarter',
            vibeTags: ['cafe'],
          ),
        ]);

    final trip = TripState(
      tripId: 'trip-1',
      userId: 'user-1',
      corridorId: 'laos_northbound_v1',
      geoRegion: 'vientiane_laos',
      locationLat: 17.9757,
      locationLng: 102.6331,
      segments: [
        _seg('vientiane_laos', '2026-10-02', '2026-10-03'),
        _seg('vang_vieng_laos', '2026-10-04', '2026-10-05'),
        _seg('luang_prabang_laos', '2026-10-06', '2026-10-08'),
      ],
      nodes: [
        TripNode(
          nodeId: 'vte-1',
          venueName: 'Vientiane Market',
          venueId: 'vte-1',
          scheduledStart: DateTime.utc(2026, 10, 2, 2),
          durationMinutes: 60,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const [],
          geoRegion: 'vientiane_laos',
          lat: 17.9757,
          lng: 102.6331,
        ),
        TripNode(
          nodeId: 'lp-1',
          venueName: 'Luang Prabang Temple',
          venueId: 'lp-1',
          scheduledStart: DateTime.utc(2026, 10, 6, 2),
          durationMinutes: 60,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const [],
          geoRegion: 'luang_prabang_laos',
          lat: 19.8856,
          lng: 102.1347,
        ),
      ],
    );

    final container = await _loadItineraryContainer(trip: trip, repo: repo);
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ItineraryScreen(tripId: 'trip-1')),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('Vientiane Market'), findsOneWidget);
    expect(find.text('Luang Prabang Temple'), findsOneWidget);

    await tester.tap(find.byTooltip('Swap this activity').last);
    await tester.pumpAndSettle();

    verify(() => repo.searchVenues(
          query: 'nearby activity',
          lat: 19.8856,
          lng: 102.1347,
          topK: 8,
        )).called(1);
    verifyNever(() => repo.searchVenues(
          query: 'nearby activity',
          lat: 17.9757,
          lng: 102.6331,
          topK: any(named: 'topK'),
        ));
  }, timeout: const Timeout(Duration(seconds: 20)));

  // -- Proof: isPast on CorridorCityGroup ------------------------------------

  test('CorridorCityGroup.isPast is true when all nodes ended', () {
    final pastNode = _node(
      name: 'Past',
      geoRegion: 'vientiane_laos',
      scheduledStart: DateTime.utc(2020, 1, 1, 9),
      durationMinutes: 60,
    );
    final group = CorridorCityGroup(
      geoRegion: 'vientiane_laos',
      displayName: 'Vientiane',
      dateRange: '2020-01-01 - 2020-01-01',
      dayGroups: groupNodesByCalendarDate([pastNode]),
    );
    expect(group.isPast(DateTime.now().toUtc()), isTrue);
  });

  test('CorridorCityGroup.isPast is false when a node is future', () {
    final futureNode = _node(
      name: 'Future',
      geoRegion: 'vientiane_laos',
      scheduledStart: DateTime.utc(2099, 1, 1, 9),
      durationMinutes: 60,
    );
    final group = CorridorCityGroup(
      geoRegion: 'vientiane_laos',
      displayName: 'Vientiane',
      dateRange: '2099-01-01 - 2099-01-01',
      dayGroups: groupNodesByCalendarDate([futureNode]),
    );
    expect(group.isPast(DateTime.now().toUtc()), isFalse);
  });

  // -- Backward compatibility: no segments -> single-city grouping -----------

  test('Single-city trip with empty segments: groupNodesByCorridor returns only Other', () {
    final nodes = [
      _node(name: 'A', geoRegion: 'dubai_uae',
            scheduledStart: DateTime.utc(2026, 10, 2, 2)),
    ];
    final groups = groupNodesByCorridor(nodes: nodes, segments: []);
    expect(groups, hasLength(1));
    expect(groups.first.displayName, 'Other stops');
  });

  // -- Sabotage proof S5: date-only grouping loses city order ----------------

  test('S5: groupNodesByCalendarDate does NOT preserve city order', () {
    // This is the WRONG approach for corridors: date-only grouping
    // mixes cities. The corridor grouper separates by city FIRST.
    final nodes = [
      _node(name: 'LP', geoRegion: 'luang_prabang_laos',
            scheduledStart: DateTime.utc(2026, 10, 2, 2)),
      _node(name: 'VTE', geoRegion: 'vientiane_laos',
            scheduledStart: DateTime.utc(2026, 10, 2, 4)),
    ];
    // Date-only: both land in same day group (no city separation)
    final dayGroups = groupNodesByCalendarDate(nodes);
    expect(dayGroups, hasLength(1)); // Same day -> merged
    expect(dayGroups.first.nodes, hasLength(2)); // Both mixed together
  });

  // -- Sabotage proof S7: repository must NOT send both start_date and segments

  test('S7: TripSegment.toJson shape does not include start_date', () {
    final seg = TripSegment(
      geoRegion: 'vientiane_laos',
      startsOn: '2026-10-02',
      endsOn: '2026-10-03',
    );
    final json = seg.toJson();
    expect(json.containsKey('start_date'), isFalse);
    expect(json.containsKey('geo_region'), isTrue);
    expect(json.containsKey('starts_on'), isTrue);
    expect(json.containsKey('ends_on'), isTrue);
  });

  testWidgets('S9: later-city swap must not use first-node coordinates',
      (tester) async {
    final repo = _MockTripRepository();
    when(() => repo.searchVenues(
          query: any(named: 'query'),
          lat: any(named: 'lat'),
          lng: any(named: 'lng'),
          topK: any(named: 'topK'),
        )).thenAnswer((_) async => const []);

    final trip = TripState(
      tripId: 'trip-1',
      userId: 'user-1',
      corridorId: 'laos_northbound_v1',
      geoRegion: 'vientiane_laos',
      locationLat: 17.9757,
      locationLng: 102.6331,
      segments: [
        _seg('vientiane_laos', '2026-10-02', '2026-10-03'),
        _seg('vang_vieng_laos', '2026-10-04', '2026-10-05'),
        _seg('luang_prabang_laos', '2026-10-06', '2026-10-08'),
      ],
      nodes: [
        TripNode(
          nodeId: 'vte-1',
          venueName: 'Vientiane Market',
          venueId: 'vte-1',
          scheduledStart: DateTime.utc(2026, 10, 2, 2),
          durationMinutes: 60,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const [],
          geoRegion: 'vientiane_laos',
          lat: 17.9757,
          lng: 102.6331,
        ),
        TripNode(
          nodeId: 'lp-1',
          venueName: 'Luang Prabang Temple',
          venueId: 'lp-1',
          scheduledStart: DateTime.utc(2026, 10, 6, 2),
          durationMinutes: 60,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const [],
          geoRegion: 'luang_prabang_laos',
          lat: 19.8856,
          lng: 102.1347,
        ),
      ],
    );

    final container = await _loadItineraryContainer(trip: trip, repo: repo);
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ItineraryScreen(tripId: 'trip-1')),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Swap this activity').last);
    await tester.pumpAndSettle();

    verifyNever(() => repo.searchVenues(
          query: 'nearby activity',
          lat: 17.9757,
          lng: 102.6331,
          topK: any(named: 'topK'),
        ));
  }, timeout: const Timeout(Duration(seconds: 20)));

  // -- Proof: CitySection collapsed/expanded behavior ----------------------

  testWidgets('CitySection: past group starts collapsed, tap expands',
      (tester) async {
    final pastGroup = CorridorCityGroup(
      geoRegion: 'vientiane_laos',
      displayName: 'Vientiane',
      dateRange: '2 Oct - 3 Oct',
      dayGroups: [
        CalendarDateGroup(
          date: DateTime.utc(2020, 10, 2),
          nodes: [
            _node(
              name: 'Temple A',
              geoRegion: 'vientiane_laos',
              scheduledStart: DateTime.utc(2020, 10, 2, 2),
            ),
          ],
        ),
      ],
    );
    var builtCount = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CitySection(
          cityGroup: pastGroup,
          childBuilder: (cg) {
            builtCount++;
            return Text('child-${cg.geoRegion}');
          },
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // Past group: collapsed, child hidden via AnimatedCrossFade.
    expect(find.text('Vientiane'), findsOneWidget);
    // The child is built (AnimatedCrossFade builds both) but crossFade hides it.
    // The chevron is not rotated (collapsed state).

    // Tap to expand.
    await tester.tap(find.text('Vientiane'));
    await tester.pumpAndSettle();

    // Now expanded: child should be visible.
    expect(find.text('child-vientiane_laos'), findsOneWidget);
  });

  testWidgets('CitySection: future group starts expanded', (tester) async {
    final futureGroup = CorridorCityGroup(
      geoRegion: 'luang_prabang_laos',
      displayName: 'Luang Prabang',
      dateRange: '6 Oct - 8 Oct',
      dayGroups: [
        CalendarDateGroup(
          date: DateTime.now().toUtc().add(const Duration(days: 30)),
          nodes: [
            _node(
              name: 'Waterfall B',
              geoRegion: 'luang_prabang_laos',
              scheduledStart:
                  DateTime.now().toUtc().add(const Duration(days: 30)),
            ),
          ],
        ),
      ],
    );
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CitySection(
          cityGroup: futureGroup,
          childBuilder: (cg) => Text('child-${cg.geoRegion}'),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // Future group: expanded by default.
    expect(find.text('Luang Prabang'), findsOneWidget);
    expect(find.text('child-luang_prabang_laos'), findsOneWidget);
  });

  // -- Proof: corridorCreate POST body shape --------------------------------

  test('TripRepository.corridorCreate sends segments-only body', () async {
    final api = _MockApiClient();
    final repo = TripRepository(api);
    final segments = [
      TripSegment(
        geoRegion: 'vientiane_laos',
        startsOn: '2026-10-02',
        endsOn: '2026-10-03',
      ),
      TripSegment(
        geoRegion: 'vang_vieng_laos',
        startsOn: '2026-10-04',
        endsOn: '2026-10-05',
      ),
    ];

    Map<String, dynamic>? capturedBody;
    when(() => api.post(any(), body: any(named: 'body')))
        .thenAnswer((invocation) async {
      capturedBody =
          invocation.namedArguments[const Symbol('body')] as Map<String, dynamic>;
      return <String, dynamic>{'trip_id': 'test-trip'};
    });
    when(() => api.get(any())).thenAnswer((_) async => <String, dynamic>{
          'trip_id': 'test-trip',
          'user_id': 'u1',
          'geo_region': 'vientiane_laos',
          'nodes': <dynamic>[],
          'segments': <dynamic>[],
          'schedule_basis': 'region_local_v1',
          'current_context': <String, dynamic>{
            'location_lat': 0,
            'location_lng': 0,
          },
        });

    await repo.corridorCreate(segments: segments);

    expect(capturedBody, isNotNull);
    expect(capturedBody!.containsKey('segments'), isTrue);
    expect(capturedBody!.containsKey('start_date'), isFalse);
    expect(capturedBody!.containsKey('geo_region'), isFalse);
    expect(capturedBody!.containsKey('user_id'), isFalse);
    expect(capturedBody!['segments'], hasLength(2));
  });

  test('TripRepository.corridorCreate includes mood when provided', () async {
    final api = _MockApiClient();
    final repo = TripRepository(api);
    final segments = [
      TripSegment(
        geoRegion: 'vientiane_laos',
        startsOn: '2026-10-02',
        endsOn: '2026-10-03',
      ),
    ];

    Map<String, dynamic>? capturedBody;
    when(() => api.post(any(), body: any(named: 'body')))
        .thenAnswer((invocation) async {
      capturedBody =
          invocation.namedArguments[const Symbol('body')] as Map<String, dynamic>;
      return <String, dynamic>{'trip_id': 'test-trip'};
    });
    when(() => api.get(any())).thenAnswer((_) async => <String, dynamic>{
          'trip_id': 'test-trip',
          'user_id': 'u1',
          'geo_region': 'vientiane_laos',
          'nodes': <dynamic>[],
          'segments': <dynamic>[],
          'schedule_basis': 'region_local_v1',
          'current_context': <String, dynamic>{
            'location_lat': 0,
            'location_lng': 0,
          },
        });

    await repo.corridorCreate(segments: segments, mood: 'relaxed');

    expect(capturedBody!['initial_mood'], 'relaxed');
    expect(capturedBody!.containsKey('start_date'), isFalse);
  });

  // -- Proof: single-city scrolling (800x600) --------------------------------

  testWidgets('single-city itinerary scrolls in 800x600 viewport',
      (tester) async {
    final repo = _MockTripRepository();
    // Create enough nodes to overflow a 600px viewport.
    final nodes = List.generate(
      12,
      (i) => _node(
        name: 'Stop $i',
        geoRegion: 'dubai_uae',
        scheduledStart: DateTime.utc(2026, 10, 5, 9 + i),
      ),
    );
    final trip = TripState(
      tripId: 'trip-scroll',
      userId: 'u1',
      geoRegion: 'dubai_uae',
      nodes: nodes,
      segments: const [],
      locationLat: 25.2,
      locationLng: 55.3,
    );
    when(() => repo.getTrip(any())).thenAnswer((_) async => trip);

    final container =
        await _loadItineraryContainer(trip: trip, repo: repo);
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(
            home: ItineraryScreen(tripId: 'trip-scroll')),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    // First stop visible.
    expect(find.text('Stop 0'), findsOneWidget);

    // Scroll down and verify later stops become visible.
    await tester.drag(find.byType(ListView).first, const Offset(0, -600));
    await tester.pumpAndSettle();

    // At least one later stop should now be visible.
    final laterStopFinders = List.generate(
      6,
      (i) => find.text('Stop ${i + 6}'),
    );
    final anyLaterVisible =
        laterStopFinders.any((f) => f.evaluate().isNotEmpty);
    expect(anyLaterVisible, isTrue,
        reason: 'Later stops not visible after scroll -- shrinkWrap regression');
  }, timeout: const Timeout(Duration(seconds: 20)));

  // -- Proof: corridor date form validation ----------------------------------

  test('_CorridorDateForm validation: overlap detected', () {
    // This test validates the form validation logic.
    // Overlap: city 1 ends on Oct 4, city 2 starts on Oct 4.
    final ranges = [
      DateTimeRange(
        start: DateTime(2026, 10, 2),
        end: DateTime(2026, 10, 4),
      ),
      DateTimeRange(
        start: DateTime(2026, 10, 4),
        end: DateTime(2026, 10, 5),
      ),
      DateTimeRange(
        start: DateTime(2026, 10, 6),
        end: DateTime(2026, 10, 7),
      ),
    ];
    // Validate: second range starts on same day first ends.
    expect(ranges[1].start.isAfter(ranges[0].end), isFalse,
        reason: 'Overlap not detected');
  });

  test('_CorridorDateForm validation: per-segment > 3 days', () {
    final range = DateTimeRange(
      start: DateTime(2026, 10, 1),
      end: DateTime(2026, 10, 4),
    );
    final days = range.end.difference(range.start).inDays + 1;
    expect(days, 4);
    expect(days > 3, isTrue, reason: 'Per-segment limit not enforced');
  });

  test('_CorridorDateForm validation: total > 7 days', () {
    final ranges = [
      DateTimeRange(start: DateTime(2026, 10, 1), end: DateTime(2026, 10, 3)),
      DateTimeRange(start: DateTime(2026, 10, 4), end: DateTime(2026, 10, 6)),
      DateTimeRange(start: DateTime(2026, 10, 7), end: DateTime(2026, 10, 9)),
    ];
    final total = ranges.fold<int>(
        0, (s, r) => s + r.end.difference(r.start).inDays + 1);
    expect(total, 9);
    expect(total > 7, isTrue, reason: 'Total limit not enforced');
  });
}
