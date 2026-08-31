import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _BlockingEnqueueDatabase extends OfflineDatabase {
  final enqueueStarted = Completer<void>();
  final releaseEnqueue = Completer<void>();

  _BlockingEnqueueDatabase() : super(testPath: inMemoryDatabasePath);

  @override
  Future<void> enqueue(
    String signalId,
    String payloadJson,
    String capturedAt,
  ) async {
    if (!enqueueStarted.isCompleted) enqueueStarted.complete();
    await releaseEnqueue.future;
    await super.enqueue(signalId, payloadJson, capturedAt);
  }
}

class _FailingOutcomeDatabase extends OfflineDatabase {
  _FailingOutcomeDatabase() : super(testPath: inMemoryDatabasePath);

  @override
  Future<void> upsertNodeOutcome({
    required String identityScope,
    required String tripId,
    required String nodeId,
    required String outcome,
    String? reason,
    DateTime? recordedAt,
  }) =>
      Future<void>.error(StateError('outcome write failed'));
}

class _FailingEnqueueDatabase extends OfflineDatabase {
  _FailingEnqueueDatabase() : super(testPath: inMemoryDatabasePath);

  @override
  Future<void> enqueue(
    String signalId,
    String payloadJson,
    String capturedAt,
  ) =>
      Future<void>.error(StateError('outbox write failed'));
}

TripNode _node({
  String id = 'node-1',
  bool locked = false,
  DateTime? start,
  int durationMinutes = 60,
}) =>
    TripNode(
      nodeId: id,
      venueName: 'Museum',
      venueId: 'museum-ref',
      scheduledStart:
          start ?? DateTime.now().toUtc().subtract(const Duration(minutes: 10)),
      durationMinutes: durationMinutes,
      isLocked: locked,
      status: NodeStatus.pending,
      vibeTags: const [],
    );

TripEventResult _eventResult(TripNode node) => TripEventResult(
      message: 'Updated',
      updatedNodes: [node],
      routingTier: 'heavy',
      fromCache: false,
    );

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  setUpAll(() => registerFallbackValue(EventType.askInfo));

  late _MockTripRepository repository;
  late _MockApiClient api;
  late OfflineDatabase database;
  late SyncEngine syncEngine;
  late ProviderContainer container;
  late TripNode node;

  setUp(() {
    repository = _MockTripRepository();
    api = _MockApiClient();
    database = OfflineDatabase(testPath: inMemoryDatabasePath);
    syncEngine = SyncEngine(db: database, api: api);
    node = _node();
    when(() => repository.getTrip('trip-1')).thenAnswer(
      (_) async => TripState(
        tripId: 'trip-1',
        userId: 'user-1',
        nodes: [node],
      ),
    );
    when(() => api.post(any(), body: any(named: 'body')))
        .thenThrow(const NetworkException());
  });

  tearDown(() async {
    container.dispose();
    syncEngine.stop();
    await database.close();
  });

  ProviderContainer makeContainer() {
    final signalService = SignalService(db: database, syncEngine: syncEngine);
    container = ProviderContainer(
      overrides: [
        tripRepoProvider.overrideWithValue(repository),
        offlineDatabaseProvider.overrideWithValue(database),
        identityCacheScopeProvider.overrideWithValue('account:user-1'),
        signalServiceProvider.overrideWithValue(signalService),
      ],
    );
    return container;
  }

  Future<ItineraryController> ready() async {
    final loaded = Completer<void>();
    final subscription = container.listen(
      itineraryControllerProvider('trip-1'),
      (_, next) {
        if (!next.loading && !loaded.isCompleted) loaded.complete();
      },
      fireImmediately: true,
    );
    addTearDown(subscription.close);
    final controller =
        container.read(itineraryControllerProvider('trip-1').notifier);
    await loaded.future;
    return controller;
  }

  Future<Map<String, dynamic>> onlySignalPayload() async {
    final rows = await (await database.db).query('outbox');
    expect(rows, hasLength(1));
    return jsonDecode(rows.single['payload_json'] as String)
        as Map<String, dynamic>;
  }

  test('restore hydrates local outcomes without emitting a signal', () async {
    await database.upsertNodeOutcome(
      identityScope: 'account:user-1',
      tripId: 'trip-1',
      nodeId: node.nodeId,
      outcome: NodeOutcome.visited,
    );
    makeContainer();

    final controller = await ready();

    expect(controller.state.nodeOutcomes[node.nodeId]?.wasVisited, isTrue);
    expect(controller.state.nodes.single.status, NodeStatus.pending);
    expect(await database.getOutboxSize(), 0);
  });

  test('visited tap enqueues once and persists one overlay outcome', () async {
    makeContainer();
    final controller = await ready();

    await controller.recordVisited(node);

    final payload = await onlySignalPayload();
    final outcomes = await database.getNodeOutcomes(
      identityScope: 'account:user-1',
      tripId: 'trip-1',
    );
    expect(payload['signal_type'], 'visited_confirmed');
    expect(outcomes, hasLength(1));
    expect(outcomes[node.nodeId]?.wasVisited, isTrue);
    expect(controller.state.nodes.single.status, NodeStatus.pending);
  });

  test('skipped tap enqueues once with the selected reason', () async {
    node = _node(start: DateTime.now().toUtc().subtract(const Duration(hours: 2)));
    when(() => repository.getTrip('trip-1')).thenAnswer(
      (_) async => TripState(
        tripId: 'trip-1',
        userId: 'user-1',
        nodes: [node],
      ),
    );
    makeContainer();
    final controller = await ready();

    await controller.recordSkipped(node, 'weather');

    final payload = await onlySignalPayload();
    expect(payload['signal_type'], 'node_skipped');
    expect(payload['value_json'], {'reason': 'weather'});
    expect(controller.state.nodeOutcomes[node.nodeId]?.reason, 'weather');
  });

  test('double tap while recording enqueues only once', () async {
    syncEngine.stop();
    await database.close();
    database = _BlockingEnqueueDatabase();
    syncEngine = SyncEngine(db: database, api: api);
    makeContainer();
    final controller = await ready();
    final blockingDb = database as _BlockingEnqueueDatabase;

    final first = controller.recordVisited(node);
    await blockingDb.enqueueStarted.future;
    await controller.recordVisited(node);
    blockingDb.releaseEnqueue.complete();
    await first;

    await onlySignalPayload();
  });

  test('failed enqueue leaves outcome visible for retry and unpersisted',
      () async {
    syncEngine.stop();
    await database.close();
    database = _FailingEnqueueDatabase();
    syncEngine = SyncEngine(db: database, api: api);
    makeContainer();
    final controller = await ready();

    await controller.recordVisited(node);
    await controller.recordSkipped(node, 'weather');

    expect(controller.state.nodeOutcomes, isEmpty);
    expect(controller.state.outcomeRecordingNodeIds, isEmpty);
    expect(controller.state.banner, contains('Could not record'));
    expect(
      await database.getNodeOutcomes(
        identityScope: 'account:user-1',
        tripId: 'trip-1',
      ),
      isEmpty,
    );
    expect(await database.getOutboxSize(), 0);
    verifyNever(() => repository.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        ));
  });

  test('elapsed skip sends no structural event', () async {
    node = _node(
      start: DateTime.now().toUtc().subtract(const Duration(hours: 2)),
      durationMinutes: 30,
    );
    when(() => repository.getTrip('trip-1')).thenAnswer(
      (_) async => TripState(
        tripId: 'trip-1',
        userId: 'user-1',
        nodes: [node],
      ),
    );
    makeContainer();
    final controller = await ready();

    await controller.recordSkipped(node, 'ran_out_of_time');

    verifyNever(() => repository.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        ));
  });

  test('locked active skip sends no structural event', () async {
    node = _node(locked: true);
    when(() => repository.getTrip('trip-1')).thenAnswer(
      (_) async => TripState(
        tripId: 'trip-1',
        userId: 'user-1',
        nodes: [node],
      ),
    );
    makeContainer();
    final controller = await ready();

    await controller.recordSkipped(node, 'too_far');

    verifyNever(() => repository.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        ));
  });

  test('active unlocked skip sends one cancel for the same node', () async {
    when(() => repository.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer((_) async => _eventResult(node));
    makeContainer();
    final controller = await ready();

    await controller.recordSkipped(node, 'crowded');

    verify(() => repository.sendEvent(
          tripId: 'trip-1',
          type: EventType.cancelActivity,
          message: any(named: 'message'),
          targetNodeId: node.nodeId,
          preferences: null,
        )).called(1);
  });

  test('persistence failure keeps the in-memory acknowledgement', () async {
    syncEngine.stop();
    await database.close();
    database = _FailingOutcomeDatabase();
    syncEngine = SyncEngine(db: database, api: api);
    makeContainer();
    final controller = await ready();

    await controller.recordVisited(node);

    expect(controller.state.nodeOutcomes[node.nodeId]?.wasVisited, isTrue);
    expect(controller.state.banner, contains('Could not save'));
    expect(await database.getOutboxSize(), 1);
  });

  test('active skip preserves persistence warning after structural event',
      () async {
    syncEngine.stop();
    await database.close();
    database = _FailingOutcomeDatabase();
    syncEngine = SyncEngine(db: database, api: api);
    when(() => repository.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer((_) async => _eventResult(node));
    makeContainer();
    final controller = await ready();

    await controller.recordSkipped(node, 'weather');

    expect(controller.state.nodeOutcomes[node.nodeId]?.wasSkipped, isTrue);
    expect(controller.state.banner, contains('Could not save'));
    verify(() => repository.sendEvent(
          tripId: 'trip-1',
          type: EventType.cancelActivity,
          message: any(named: 'message'),
          targetNodeId: node.nodeId,
          preferences: null,
        )).called(1);
  });
}
