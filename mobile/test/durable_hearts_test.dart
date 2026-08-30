import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/debug/sync_status_screen.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';

// Mocks
class MockTripRepository extends Mock implements TripRepository {}

class MockApiClient extends Mock implements ApiClient {}

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
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // ============================================================
  // Group A: Durable Hearts
  // ============================================================

  group('Durable hearts', () {
    late OfflineDatabase realDb;
    late MockTripRepository repo;

    setUp(() {
      realDb = OfflineDatabase(testPath: inMemoryDatabasePath);
      repo = MockTripRepository();
      when(() => repo.getTrip('t1'))
          .thenAnswer((_) async => _trip([_node('n1', 'Old Souk')]));
    });

    tearDown(() async {
      await realDb.close();
    });

    ProviderContainer _container({String scope = 'account:user-a'}) {
      final c = ProviderContainer(
        overrides: [
          tripRepoProvider.overrideWithValue(repo),
          offlineDatabaseProvider.overrideWithValue(realDb),
          identityCacheScopeProvider.overrideWithValue(scope),
        ],
      );
      addTearDown(c.dispose);
      return c;
    }

    /// Keep a subscription open so autoDispose does NOT tear down mid-test.
    Future<ItineraryController> ready(
      ProviderContainer container, [
      String tripId = 't1',
    ]) async {
      final sub = container.listen(
        itineraryControllerProvider(tripId),
        (_, __) {},
        fireImmediately: true,
      );
      addTearDown(sub.close);
      final c =
          container.read(itineraryControllerProvider(tripId).notifier);
      await Future<void>.delayed(const Duration(milliseconds: 50));
      return c;
    }

    // ----------------------------------------------------------
    // Test 1: Loved refs survive controller recreation
    // ----------------------------------------------------------
    test('loved refs survive controller recreation', () async {
      final c1 = _container();
      final ctrl1 = await ready(c1);

      // User taps heart (production path: emit + markLoved)
      ctrl1.markLoved('souk-ref');
      expect(
        c1.read(itineraryControllerProvider('t1')).lovedPlaceRefs,
        contains('souk-ref'),
      );

      // Wait for async persistence
      await Future<void>.delayed(const Duration(milliseconds: 50));

      // Dispose and recreate (simulates navigation away + back)
      c1.dispose();
      final c2 = _container();
      await ready(c2);

      // Heart must be restored from SQLite
      expect(
        c2.read(itineraryControllerProvider('t1')).lovedPlaceRefs,
        contains('souk-ref'),
      );
    });

    // ----------------------------------------------------------
    // Test 2: Restore does not enqueue another signal
    // ----------------------------------------------------------
    test('restore does not enqueue another signal', () async {
      final c1 = _container();
      final ctrl1 = await ready(c1);

      // Real user action: emit signal + persist love
      final signalService = SignalService(
        db: realDb,
        syncEngine: SyncEngine(
          db: realDb,
          api: MockApiClient(),
        ),
      );
      await signalService.emitUserLoved(placeRef: 'souk-ref', tripId: 't1');
      ctrl1.markLoved('souk-ref');
      await Future<void>.delayed(const Duration(milliseconds: 50));

      // Record outbox size after the real emission
      final sizeAfterEmit = await realDb.getOutboxSize();

      // Dispose and recreate -- this triggers restore
      c1.dispose();
      final c2 = _container();
      await ready(c2);

      // Outbox size must not have grown (restore emits no signal)
      final sizeAfterRestore = await realDb.getOutboxSize();
      expect(sizeAfterRestore, sizeAfterEmit);
    });

    // ----------------------------------------------------------
    // Test 3: Reload preserves love (same controller)
    // ----------------------------------------------------------
    test('reload preserves love on same controller', () async {
      final c = _container();
      final ctrl = await ready(c);

      ctrl.markLoved('souk-ref');
      expect(
        c.read(itineraryControllerProvider('t1')).lovedPlaceRefs,
        contains('souk-ref'),
      );

      // Call load() again on the same controller
      await ctrl.load();
      await Future<void>.delayed(const Duration(milliseconds: 50));

      expect(
        c.read(itineraryControllerProvider('t1')).lovedPlaceRefs,
        contains('souk-ref'),
      );
    });

    // ----------------------------------------------------------
    // Test 4: Identity and trip isolation
    // ----------------------------------------------------------
    test('identity and trip isolation', () async {
      // Persist for scope A / trip t1
      await realDb.upsertLovedPlace(
        identityScope: 'account:a',
        tripId: 't1',
        placeRef: 'souk-ref',
      );

      // Scope B must not see it
      final scopeB = await realDb.getLovedPlaceRefs(
        identityScope: 'account:b',
        tripId: 't1',
      );
      expect(scopeB, isEmpty);

      // Trip t2 must not see it
      final tripT2 = await realDb.getLovedPlaceRefs(
        identityScope: 'account:a',
        tripId: 't2',
      );
      expect(tripT2, isEmpty);

      // Scope A / trip t1 sees it
      final correct = await realDb.getLovedPlaceRefs(
        identityScope: 'account:a',
        tripId: 't1',
      );
      expect(correct, contains('souk-ref'));
    });

    // ----------------------------------------------------------
    // Test 5: DB failure in restore does not break trip loading
    // ----------------------------------------------------------
    test('getLovedPlaceRefs failure still loads trip with empty loved refs', () async {
      // Use a fresh DB that we sabotage after setup
      final brokenDb = OfflineDatabase(testPath: inMemoryDatabasePath);
      addTearDown(() async => await brokenDb.close());

      final brokenRepo = MockTripRepository();
      when(() => brokenRepo.getTrip('t1'))
          .thenAnswer((_) async => _trip([_node('n1', 'Old Souk')]));

      // Close the DB to make getLovedPlaceRefs throw
      await brokenDb.db; // force open first
      await brokenDb.close();

      final c = ProviderContainer(
        overrides: [
          tripRepoProvider.overrideWithValue(brokenRepo),
          offlineDatabaseProvider.overrideWithValue(brokenDb),
          identityCacheScopeProvider.overrideWithValue('account:user-a'),
        ],
      );
      addTearDown(c.dispose);

      final sub = c.listen(
        itineraryControllerProvider('t1'),
        (_, __) {},
        fireImmediately: true,
      );
      addTearDown(sub.close);
      await Future<void>.delayed(const Duration(milliseconds: 100));

      final state = c.read(itineraryControllerProvider('t1'));
      // Trip must still load successfully (nodes present, no error)
      expect(state.loading, false);
      expect(state.error, isNull);
      expect(state.nodes, isNotEmpty);
      expect(state.lovedPlaceRefs, isEmpty);
    });
  });

  // ============================================================
  // Group B: Sync status awaits sync
  // ============================================================

  group('Sync status refresh', () {
    test('refresh waits before counts', () async {
      final db = OfflineDatabase(testPath: inMemoryDatabasePath);
      addTearDown(() async => await db.close());

      final mockApi = MockApiClient();
      final engine = SyncEngine(db: db, api: mockApi);
      addTearDown(engine.stop);

      // Enqueue one event
      await db.enqueue(
        'sig-1',
        jsonEncode({'signal_type': 'user_loved', 'place_ref': 'x'}),
        DateTime.now().toUtc().toIso8601String(),
      );

      // Mock API: success but delayed
      when(() => mockApi.post(any(), body: any(named: 'body')))
          .thenAnswer((_) async {
        await Future.delayed(const Duration(milliseconds: 100));
        return {'accepted': 1, 'duplicates': 0, 'rejected': []};
      });

      // Use the extracted refreshSyncStatus helper
      final counts = await refreshSyncStatus(engine);

      // Because we awaited syncOnce, the row should be deleted (synced).
      // Pending must be 0, not 1.
      expect(counts['pending'] ?? 0, 0);
    });
  });

  // ============================================================
  // Group C: 401 halts second POST
  // ============================================================

  group('401 auth halt', () {
    test('401 blocks a second POST', () async {
      final db = OfflineDatabase(testPath: inMemoryDatabasePath);
      addTearDown(() async => await db.close());

      final mockApi = MockApiClient();
      final engine = SyncEngine(db: db, api: mockApi);
      addTearDown(engine.stop);

      // Enqueue two events
      await db.enqueue(
        'sig-a',
        jsonEncode({'signal_type': 'user_loved', 'place_ref': 'a'}),
        DateTime.now().toUtc().toIso8601String(),
      );
      await db.enqueue(
        'sig-b',
        jsonEncode({'signal_type': 'user_loved', 'place_ref': 'b'}),
        DateTime.now().toUtc().toIso8601String(),
      );

      int postCount = 0;
      when(() => mockApi.post(any(), body: any(named: 'body')))
          .thenAnswer((_) async {
        postCount++;
        throw const UnauthorizedException('Token expired');
      });

      // First sync: hits 401
      await engine.syncOnce();
      expect(engine.authHalted, true);
      expect(postCount, 1);

      // Second sync: should NOT attempt POST (auth halted)
      await engine.syncOnce();
      expect(postCount, 1); // Still 1 -- no second POST

      // Events must be preserved (pending, not deleted)
      final counts = await engine.getStatusCounts();
      expect(counts['pending'] ?? 0, greaterThan(0));

      // After resetAuthHalted, a manual attempt may run
      engine.resetAuthHalted();
      expect(engine.authHalted, false);

      // Next sync attempt will try POST again
      await engine.syncOnce();
      expect(postCount, 2); // Now 2 -- one more POST attempted
    });
  });
}
