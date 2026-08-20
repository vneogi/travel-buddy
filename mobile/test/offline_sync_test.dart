import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';

// Mocks
class MockApiClient extends Mock implements ApiClient {}

/// SPEC-02 Part D — Offline queue tests.
///
/// Uses in-memory SQLite (`:memory:`) for full test isolation —
/// each test gets a fresh empty database.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  late OfflineDatabase db;
  late MockApiClient mockApi;
  late SyncEngine syncEngine;
  late SignalService signalService;

  setUp(() async {
    db = OfflineDatabase(testPath: inMemoryDatabasePath);
    mockApi = MockApiClient();
    syncEngine = SyncEngine(db: db, api: mockApi);
    signalService = SignalService(db: db, syncEngine: syncEngine);
  });

  tearDown(() async {
    syncEngine.stop();
    // Let any fire-and-forget triggerSync() settle before closing DB
    await Future.delayed(const Duration(milliseconds: 50));
    await db.close();
  });

  // ============================================================
  // Test 1: emit with network DOWN -> row in outbox, no throw
  // ============================================================
  test('1. emit persists to outbox before network (durability guarantee)', () async {
    // Stub API to simulate offline (triggerSync runs in background)
    when(() => mockApi.post(any(), body: any(named: 'body')))
        .thenThrow(const NetworkException());

    await signalService.emit(
      signalType: 'user_loved',
      placeRef: 'dubai-mall',
      valueText: 'loved',
      tripId: 'trip-001',
    );

    // Verify: row is in outbox with state 'pending'
    final batch = await db.getPendingBatch();
    expect(batch.length, 1);
    expect(batch.first['state'], 'pending');

    // Verify: payload contains correct data
    final payload = jsonDecode(batch.first['payload_json'] as String);
    expect(payload['signal_type'], 'user_loved');
    expect(payload['place_ref'], 'dubai-mall');
    expect(payload['signal_id'], isNotEmpty);
  });

  // ============================================================
  // Test 2: connectivity restored -> sync posts batch -> outbox empty
  // ============================================================
  test('2. sync posts batch and clears outbox on success', () async {
    await db.enqueue('sig-001', jsonEncode({
      'signal_id': 'sig-001',
      'signal_type': 'user_loved',
      'place_ref': 'burj-khalifa',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenAnswer((_) async => {'accepted': 1, 'duplicates': 0, 'rejected': []});

    final worked = await syncEngine.syncOnce();
    expect(worked, true);

    final remaining = await db.getPendingBatch();
    expect(remaining, isEmpty);
  });

  // ============================================================
  // Test 3: duplicate safety — re-post after interrupted delete
  // ============================================================
  test('3. duplicate signal_id tolerates server duplicate response', () async {
    await db.enqueue('sig-dup', jsonEncode({
      'signal_id': 'sig-dup',
      'signal_type': 'user_loved',
      'place_ref': 'la-mer',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenAnswer((_) async => {'accepted': 0, 'duplicates': 1, 'rejected': []});

    final worked = await syncEngine.syncOnce();
    expect(worked, true);

    final remaining = await db.getPendingBatch();
    expect(remaining, isEmpty);
  });

  // ============================================================
  // Test 4: crash recovery — inflight rows reset to pending on startup
  // ============================================================
  test('4. crash recovery: inflight rows reset to pending', () async {
    await db.enqueue('sig-crash', jsonEncode({
      'signal_id': 'sig-crash',
      'signal_type': 'user_loved',
      'place_ref': 'old-souk',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());
    await db.markInflight(['sig-crash']);

    final before = await db.getPendingBatch();
    expect(before, isEmpty);

    final recovered = await db.recoverInflight();
    expect(recovered, 1);

    final after = await db.getPendingBatch();
    expect(after.length, 1);
    expect(after.first['signal_id'], 'sig-crash');
  });

  // ============================================================
  // Test 5: backoff — ServerException increments attempts, row not lost
  // ============================================================
  test('5. transient failure (ServerException): attempts increment, row not lost', () async {
    await db.enqueue('sig-retry', jsonEncode({
      'signal_id': 'sig-retry',
      'signal_type': 'user_loved',
      'place_ref': 'palm-jumeirah',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(const ServerException());

    await syncEngine.syncOnce();

    final database = await db.db;
    final rows = await database.query('outbox', where: "signal_id = 'sig-retry'");
    expect(rows.length, 1);
    expect(rows.first['state'], 'pending');
    expect(rows.first['attempts'] as int, greaterThan(0));
    expect(rows.first['next_retry_at'], isNotNull);
  });

  // ============================================================
  // Test 6: permanent failure — ForbiddenException -> failed_permanent
  // ============================================================
  test('6. permanent failure (ForbiddenException): marked failed_permanent', () async {
    await db.enqueue('sig-bad', jsonEncode({
      'signal_id': 'sig-bad',
      'signal_type': 'user_loved',
      'place_ref': 'nowhere',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(const ForbiddenException());

    await syncEngine.syncOnce();

    final database = await db.db;
    final rows = await database.query('outbox', where: "signal_id = 'sig-bad'");
    expect(rows.length, 1);
    expect(rows.first['state'], 'failed_permanent');

    final pending = await db.getPendingBatch();
    expect(pending, isEmpty);
  });

  // ============================================================
  // Test 7: 401 — events NOT dropped, sync halts
  // ============================================================
  test('7. auth failure (UnauthorizedException): events preserved, not retried', () async {
    await db.enqueue('sig-auth', jsonEncode({
      'signal_id': 'sig-auth',
      'signal_type': 'user_loved',
      'place_ref': 'creek',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(const UnauthorizedException());

    await syncEngine.syncOnce();

    // Event must NOT be deleted — preserved for re-auth retry
    final database = await db.db;
    final rows = await database.query('outbox', where: "signal_id = 'sig-auth'");
    expect(rows.length, 1);
    // Should be back to pending (not stuck inflight, not deleted, not failed)
    expect(rows.first['state'], 'pending');
    // Attempts should NOT increment (it's not a transient failure)
    expect(rows.first['attempts'], 0);
  });

  // ============================================================
  // Test 8: offline read — cached trip returned
  // ============================================================
  test('8. offline read: cached trip available', () async {
    await db.cacheTrip('trip-123', jsonEncode({'id': 'trip-123', 'status': 'active'}));

    final cached = await db.getCachedTrip('trip-123');
    expect(cached, isNotNull);
    final data = jsonDecode(cached!);
    expect(data['id'], 'trip-123');
    expect(data['status'], 'active');

    final missing = await db.getCachedTrip('trip-999');
    expect(missing, isNull);
  });

  // ============================================================
  // Test 9: ordering — batch sent oldest-captured_at first
  // ============================================================
  test('9. batch is ordered oldest-captured_at first', () async {
    await db.enqueue('sig-new', jsonEncode({
      'signal_id': 'sig-new',
      'signal_type': 'user_loved',
      'place_ref': 'new-venue',
      'captured_at': '2026-08-05T15:00:00Z',
    }), '2026-08-05T15:00:00Z');

    await db.enqueue('sig-old', jsonEncode({
      'signal_id': 'sig-old',
      'signal_type': 'user_loved',
      'place_ref': 'old-venue',
      'captured_at': '2026-08-05T10:00:00Z',
    }), '2026-08-05T10:00:00Z');

    final batch = await db.getPendingBatch();
    expect(batch.length, 2);
    expect(batch[0]['signal_id'], 'sig-old');
    expect(batch[1]['signal_id'], 'sig-new');
  });

  // ============================================================
  // Test 10: single-flight — concurrent syncOnce() calls = one POST
  // ============================================================
  test('10. single-flight: concurrent syncs do not double-post', () async {
    await db.enqueue('sig-sf', jsonEncode({
      'signal_id': 'sig-sf',
      'signal_type': 'user_loved',
      'place_ref': 'single-flight-test',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenAnswer((_) async {
      await Future.delayed(const Duration(milliseconds: 100));
      return {'accepted': 1, 'duplicates': 0, 'rejected': []};
    });

    final results = await Future.wait([
      syncEngine.syncOnce(),
      syncEngine.syncOnce(),
    ]);

    expect(results.where((r) => r == true).length, 1);
    expect(results.where((r) => r == false).length, 1);

    verify(() => mockApi.post('/signals', body: any(named: 'body'))).called(1);
  });

  // ============================================================
  // Test 11: NetworkException is transient (not permanent)
  // ============================================================
  test('11. network failure (NetworkException): backoff, not permanent', () async {
    await db.enqueue('sig-net', jsonEncode({
      'signal_id': 'sig-net',
      'signal_type': 'user_loved',
      'place_ref': 'marina',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(const NetworkException());

    await syncEngine.syncOnce();

    // Row should be pending with backoff (NOT failed_permanent)
    final database = await db.db;
    final rows = await database.query('outbox', where: "signal_id = 'sig-net'");
    expect(rows.length, 1);
    expect(rows.first['state'], 'pending');
    expect(rows.first['attempts'] as int, greaterThan(0));
  });

  // ============================================================
  // Test 12: resetBackoff clears attempts/next_retry_at for pending rows
  // ============================================================
  test('12. resetBackoff clears backoff so pending rows are immediately eligible', () async {
    await db.enqueue('sig-backoff', jsonEncode({
      'signal_id': 'sig-backoff',
      'signal_type': 'user_loved',
      'place_ref': 'jumeirah',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    // Simulate a failed retry (sets attempts + future next_retry_at)
    await db.markRetry(['sig-backoff'], 'transient network error');

    // Verify the row is NOT immediately eligible (backoff is in the future)
    final before = await db.getPendingBatch(limit: 10);
    expect(before.length, 0, reason: 'Should be backing off');

    // Reset backoff (simulates connectivity regained)
    final reset = await db.resetBackoff();
    expect(reset, 1);

    // Now the row should be immediately eligible
    final after = await db.getPendingBatch(limit: 10);
    expect(after.length, 1);
    expect(after.first['signal_id'], 'sig-backoff');
    // attempts preserved (was set by markRetry); only next_retry_at cleared
    expect(after.first['attempts'], isNot(0),
        reason: 'resetBackoff must not wipe attempts (sabotage test)');
    expect(after.first['next_retry_at'], isNull);
  });
  test('resetAuthHalted clears halted state allowing sync to retry', () async {
    await db.enqueue(
      'sig-auth-reset',
      jsonEncode({
        'signal_id': 'sig-auth-reset',
        'signal_type': 'user_loved',
        'place_ref': 'creek',
        'captured_at': DateTime.now().toUtc().toIso8601String(),
      }),
      DateTime.now().toUtc().toIso8601String(),
    );

    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(const UnauthorizedException());

    await syncEngine.syncOnce();
    expect(syncEngine.authHalted, isTrue);

    // resetAuthHalted clears it
    syncEngine.resetAuthHalted();
    expect(syncEngine.authHalted, isFalse);
  });

}
