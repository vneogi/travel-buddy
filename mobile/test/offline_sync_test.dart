import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/core/api_client.dart';

// Mocks
class MockApiClient extends Mock implements ApiClient {}

/// SPEC-02 Part D — Offline queue tests.
///
/// These tests verify the non-negotiable invariants:
/// 1. Never lose a user action (persist before network)
/// 2. Exactly-once server effect (idempotent retry)
/// 3. Never block UI on network
/// 4. Crash recovery (inflight rows retried)
/// 5. Backoff with jitter (no thundering herd)
void main() {
  // Use in-memory SQLite for tests
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  late OfflineDatabase db;
  late MockApiClient mockApi;
  late SyncEngine syncEngine;
  late SignalService signalService;

  setUp(() async {
    db = OfflineDatabase();
    mockApi = MockApiClient();
    syncEngine = SyncEngine(db: db, api: mockApi);
    signalService = SignalService(db: db, syncEngine: syncEngine);
  });

  tearDown(() async {
    syncEngine.stop();
    await db.close();
  });

  // ============================================================
  // Test 1: emit with network DOWN -> row in outbox, no throw
  // ============================================================
  test('1. emit persists to outbox before network (durability guarantee)', () async {
    // Don't set up any mock response — emit should NOT call network
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
    // Enqueue a signal
    await db.enqueue('sig-001', jsonEncode({
      'signal_id': 'sig-001',
      'signal_type': 'user_loved',
      'place_ref': 'burj-khalifa',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    // Mock successful response
    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenAnswer((_) async => {'accepted': 1, 'duplicates': 0, 'rejected': []});

    // Sync
    final worked = await syncEngine.syncOnce();
    expect(worked, true);

    // Outbox should be empty
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

    // Server says it's a duplicate (already has it)
    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenAnswer((_) async => {'accepted': 0, 'duplicates': 1, 'rejected': []});

    final worked = await syncEngine.syncOnce();
    expect(worked, true);

    // Row still cleared from outbox (server has it = safe to delete)
    final remaining = await db.getPendingBatch();
    expect(remaining, isEmpty);
  });

  // ============================================================
  // Test 4: crash recovery — inflight rows reset to pending on startup
  // ============================================================
  test('4. crash recovery: inflight rows reset to pending', () async {
    // Simulate crash: row stuck in 'inflight'
    await db.enqueue('sig-crash', jsonEncode({
      'signal_id': 'sig-crash',
      'signal_type': 'user_loved',
      'place_ref': 'old-souk',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());
    await db.markInflight(['sig-crash']);

    // Verify it's inflight (would be stuck without recovery)
    final before = await db.getPendingBatch();
    expect(before, isEmpty); // not visible as 'pending'

    // Crash recovery (called on startup)
    final recovered = await db.recoverInflight();
    expect(recovered, 1);

    // Now it's pending again and will be retried
    final after = await db.getPendingBatch();
    expect(after.length, 1);
    expect(after.first['signal_id'], 'sig-crash');
  });

  // ============================================================
  // Test 5: backoff — 5xx increments attempts, sets next_retry_at
  // ============================================================
  test('5. transient failure: attempts increment, row not lost', () async {
    await db.enqueue('sig-retry', jsonEncode({
      'signal_id': 'sig-retry',
      'signal_type': 'user_loved',
      'place_ref': 'palm-jumeirah',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    // Mock 500 error
    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(Exception('500 Internal Server Error'));

    await syncEngine.syncOnce();

    // Row should still exist (not lost) but with backoff
    final database = await db.db;
    final rows = await database.query('outbox', where: "signal_id = 'sig-retry'");
    expect(rows.length, 1);
    expect(rows.first['state'], 'pending');
    expect(rows.first['attempts'] as int, greaterThan(0));
    expect(rows.first['next_retry_at'], isNotNull);
  });

  // ============================================================
  // Test 6: permanent failure — 422 -> failed_permanent, not retried
  // ============================================================
  test('6. permanent failure (422): marked failed_permanent, retained', () async {
    await db.enqueue('sig-bad', jsonEncode({
      'signal_id': 'sig-bad',
      'signal_type': 'user_loved',
      'place_ref': 'nowhere',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    // Mock 422 Unprocessable Entity (whole-batch error without per-item detail)
    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(Exception('422 Unprocessable Entity'));

    await syncEngine.syncOnce();

    // Row still exists (retained for diagnostics) but marked permanent
    final database = await db.db;
    final rows = await database.query('outbox', where: "signal_id = 'sig-bad'");
    expect(rows.length, 1);
    expect(rows.first['state'], 'failed_permanent');

    // Not in pending batch (won't be retried)
    final pending = await db.getPendingBatch();
    expect(pending, isEmpty);
  });

  // ============================================================
  // Test 7: 401 — events NOT dropped, sync halts
  // ============================================================
  test('7. auth failure (401): events preserved, sync halts', () async {
    await db.enqueue('sig-auth', jsonEncode({
      'signal_id': 'sig-auth',
      'signal_type': 'user_loved',
      'place_ref': 'creek',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }), DateTime.now().toUtc().toIso8601String());

    // Mock 401 Unauthorized
    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenThrow(Exception('401 Unauthorized'));

    await syncEngine.syncOnce();

    // Event must NOT be deleted — it's preserved for re-auth retry
    final database = await db.db;
    final rows = await database.query('outbox', where: "signal_id = 'sig-auth'");
    expect(rows.length, 1);
    // Should be back to pending (not stuck inflight, not deleted)
    expect(rows.first['state'], 'pending');
  });

  // ============================================================
  // Test 8: offline read — cached trip returned with fromCache marker
  // ============================================================
  test('8. offline read: cached trip available', () async {
    // Cache a trip
    await db.cacheTrip('trip-123', jsonEncode({'id': 'trip-123', 'status': 'active'}));

    // Read it back
    final cached = await db.getCachedTrip('trip-123');
    expect(cached, isNotNull);
    final data = jsonDecode(cached!);
    expect(data['id'], 'trip-123');
    expect(data['status'], 'active');

    // Non-existent trip returns null
    final missing = await db.getCachedTrip('trip-999');
    expect(missing, isNull);
  });

  // ============================================================
  // Test 9: ordering — batch sent oldest-captured_at first
  // ============================================================
  test('9. batch is ordered oldest-captured_at first', () async {
    // Enqueue in reverse chronological order
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
    // Oldest first
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

    // Mock slow response
    when(() => mockApi.post('/signals', body: any(named: 'body')))
        .thenAnswer((_) async {
      await Future.delayed(const Duration(milliseconds: 100));
      return {'accepted': 1, 'duplicates': 0, 'rejected': []};
    });

    // Fire two concurrent syncs
    final results = await Future.wait([
      syncEngine.syncOnce(),
      syncEngine.syncOnce(),
    ]);

    // One should have worked, one should have been rejected (single-flight)
    expect(results.where((r) => r == true).length, 1);
    expect(results.where((r) => r == false).length, 1);

    // Only one POST call was made
    verify(() => mockApi.post('/signals', body: any(named: 'body'))).called(1);
  });
}
