import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mocktail/mocktail.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';

class MockTripRepository extends Mock implements TripRepository {}
class MockOfflineDatabase extends Mock implements OfflineDatabase {}

TripState _trip(List<TripNode> nodes) =>
    TripState(tripId: 't1', userId: 'u1', nodes: nodes);

TripNode _node(String id, String name) => TripNode(
      nodeId: id,
      venueName: name,
      scheduledStart: DateTime(2026, 8, 5, 9),
      durationMinutes: 90,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
    );

void main() {
  setUpAll(() => registerFallbackValue(EventType.askInfo));

  late MockTripRepository repo;
  late MockOfflineDatabase mockDb;
  late ProviderContainer container;

  setUp(() {
    repo = MockTripRepository();
    mockDb = MockOfflineDatabase();
    when(() => repo.getTrip('t1'))
        .thenAnswer((_) async => _trip([_node('n1', 'Old')]));
    when(() => mockDb.cachePlace(any(), any())).thenAnswer((_) async {});
    when(() => mockDb.getLovedPlaceRefs(
      identityScope: any(named: 'identityScope'),
      tripId: any(named: 'tripId'),
    )).thenAnswer((_) async => <String>{});
    when(() => mockDb.upsertLovedPlace(
      identityScope: any(named: 'identityScope'),
      tripId: any(named: 'tripId'),
      placeRef: any(named: 'placeRef'),
    )).thenAnswer((_) async {});
    when(() => mockDb.getCachedTrip(any())).thenAnswer((_) async => null);
    container = ProviderContainer(
      overrides: [
        tripRepoProvider.overrideWithValue(repo),
        offlineDatabaseProvider.overrideWithValue(mockDb),
        identityCacheScopeProvider.overrideWithValue('account:test'),
      ],
    );
    addTearDown(container.dispose);
  });

  /// Keep a subscription open so autoDispose does NOT tear the controller down
  /// mid-test, then let the constructor's load() future settle.
  Future<ItineraryController> ready([String tripId = 't1']) async {
    final sub = container.listen(
      itineraryControllerProvider(tripId),
      (_, __) {},
      fireImmediately: true,
    );
    addTearDown(sub.close);
    final c = container.read(itineraryControllerProvider(tripId).notifier);
    await Future<void>.delayed(const Duration(milliseconds: 10)); // let load() finish
    return c;
  }

  test('loads nodes on init', () async {
    await ready();
    final s = container.read(itineraryControllerProvider('t1'));
    expect(s.loading, false);
    expect(s.nodes.single.venueName, 'Old');
  });

  test('successful event replaces nodes and extracts Heads up banner', () async {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer((_) async => TripEventResult(
          message: 'Swapped. Heads up: New venue closes early.',
          updatedNodes: [_node('n1', 'New')],
          routingTier: 'heavy',
          fromCache: false,
        ));

    final c = await ready();
    final result = await c.applyEvent(
        type: EventType.swapActivity, message: 'swap', targetNodeId: 'n1');

    final s = container.read(itineraryControllerProvider('t1'));
    expect(result, isNotNull);
    expect(s.nodes.single.venueName, 'New');
    expect(s.banner, startsWith('Heads up:'));
    expect(s.processing, false);
  });

  test('reroute limit sets flag and returns null (no crash, no node change)',
      () async {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenThrow(const RerouteLimitException());

    final c = await ready();
    final result =
        await c.applyEvent(type: EventType.reroute, message: 'reroute everything');

    final s = container.read(itineraryControllerProvider('t1'));
    expect(result, isNull);
    expect(s.rerouteLimitHit, true);
    expect(s.nodes.single.venueName, 'Old');
  });

  test('generic error surfaces a banner, keeps nodes', () async {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenThrow(const ServerException());

    final c = await ready();
    await c.applyEvent(type: EventType.askInfo, message: 'hi');

    final s = container.read(itineraryControllerProvider('t1'));
    expect(s.banner, isNotNull);
    expect(s.nodes.single.venueName, 'Old');
  });

  test('network event error uses connection copy without leaking internals',
      () async {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenThrow(const NetworkException());

    final controller = await ready();
    await controller.applyEvent(type: EventType.askInfo, message: 'nearby');

    expect(controller.state.banner, contains("Can't reach Travel Buddy"));
    expect(controller.state.banner, isNot(contains('NetworkException')));
  });

  test('ignores a second event while the first is processing', () async {
    final pending = Completer<TripEventResult>();
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer((_) => pending.future);

    final controller = await ready();
    final first = controller.applyEvent(
      type: EventType.swapActivity,
      message: 'first',
      targetNodeId: 'n1',
    );
    final second = await controller.applyEvent(
      type: EventType.swapActivity,
      message: 'second',
      targetNodeId: 'n1',
    );

    expect(second, isNull);
    verify(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).called(1);
    pending.complete(TripEventResult(
      message: 'Done',
      updatedNodes: [_node('n1', 'New')],
      routingTier: 'heavy',
      fromCache: false,
    ));
    await first;
  });

  test('load error populates error state', () async {
    when(() => repo.getTrip('t2')).thenThrow(const NetworkException());
    await ready('t2'); // holds a listener + lets load() settle
    final s = container.read(itineraryControllerProvider('t2'));
    expect(s.error, isA<NetworkException>());
    expect(s.loading, false);
  });

  group('SPEC-04 offline cache', () {
    test('offline load falls back to cached trip when network fails', () async {
      // Make repo throw on load
      when(() => repo.getTrip('t1')).thenThrow(const NetworkException());
      // Seed cache with valid trip JSON
      final cachedTrip = TripState(
        tripId: 't1',
        userId: 'u1',
        nodes: [_node('n1', 'Cached Hotel')],
      );
      when(() => mockDb.getCachedTrip('t1'))
          .thenAnswer((_) async => jsonEncode(cachedTrip.toJson()));
      when(() => mockDb.cachePlace(any(), any())).thenAnswer((_) async {});
    when(() => mockDb.getLovedPlaceRefs(
      identityScope: any(named: 'identityScope'),
      tripId: any(named: 'tripId'),
    )).thenAnswer((_) async => <String>{});
    when(() => mockDb.upsertLovedPlace(
      identityScope: any(named: 'identityScope'),
      tripId: any(named: 'tripId'),
      placeRef: any(named: 'placeRef'),
    )).thenAnswer((_) async {});
    when(() => mockDb.getCachedTrip(any())).thenAnswer((_) async => null);

      final c = await ready();
      await Future.delayed(const Duration(milliseconds: 50));

      expect(c.state.loading, isFalse);
      expect(c.state.nodes, hasLength(1));
      expect(c.state.nodes.first.venueName, equals('Cached Hotel'));
      expect(c.state.banner, contains('Offline'));
    });

    test('successful load caches trip to SQLite cache_trip', () async {
      when(() => mockDb.cacheTrip(any(), any())).thenAnswer((_) async {});
      when(() => mockDb.cachePlace(any(), any())).thenAnswer((_) async {});
    when(() => mockDb.getLovedPlaceRefs(
      identityScope: any(named: 'identityScope'),
      tripId: any(named: 'tripId'),
    )).thenAnswer((_) async => <String>{});
    when(() => mockDb.upsertLovedPlace(
      identityScope: any(named: 'identityScope'),
      tripId: any(named: 'tripId'),
      placeRef: any(named: 'placeRef'),
    )).thenAnswer((_) async {});
    when(() => mockDb.getCachedTrip(any())).thenAnswer((_) async => null);

      await ready();
      await Future.delayed(const Duration(milliseconds: 50));

      verify(() => mockDb.cacheTrip('t1', any())).called(1);
    });
  });

}
